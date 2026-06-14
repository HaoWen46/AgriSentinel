"""Phase 1 — Sentinel-2 L2A bi-temporal ingestion (Microsoft Planetary Computer).

For each of the two low-cloud windows (``t0``, ``t1``) defined in the AOI config,
search the public Planetary Computer STAC, pick the least-cloudy scene, read just
the AOI footprint of each band onto a common 10 m grid, and store the clipped
bands + a manifest in MinIO.

No authentication is required for moderate use; a ``PC_SUBSCRIPTION_KEY`` only
raises rate limits. Run: ``uv run python -m ingestion.stac_fetch``.
"""

from __future__ import annotations

import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds as window_from_bounds

from agrisentinel.config import AOI, get_aoi, get_settings
from agrisentinel.logging import get_logger
from agrisentinel.raster import save_window
from agrisentinel.storage import ensure_bucket

log = get_logger(__name__)

PC_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
TARGET_RES_M = 10.0


def _open_catalog():
    import planetary_computer
    import pystac_client

    return pystac_client.Client.open(PC_STAC_URL, modifier=planetary_computer.sign_inplace)


def _pick_scene(catalog, aoi: AOI, window) -> object:
    search = catalog.search(
        collections=[aoi.stac.collection],
        bbox=aoi.bbox,
        datetime=f"{window.start}/{window.end}",
        query={"eo:cloud_cover": {"lt": aoi.stac.max_cloud_cover}},
    )
    items = list(search.items())
    if not items:
        raise RuntimeError(
            f"No Sentinel-2 scene found for {window.start}..{window.end} "
            f"(cloud < {aoi.stac.max_cloud_cover}%)."
        )
    items.sort(key=lambda it: it.properties.get("eo:cloud_cover", 100.0))
    best = items[0]
    log.info(
        "  picked %s (%s, cloud %.1f%%) from %d candidates",
        best.id,
        best.properties.get("datetime", "?")[:10],
        best.properties.get("eo:cloud_cover", -1),
        len(items),
    )
    return best


def _read_band(href: str, bounds_target, target_crs: str, height: int, width: int):
    with rasterio.open(href) as ds:
        # Bands of one S2 item share a CRS; window is computed in that CRS and
        # resampled to the common (height, width) grid via out_shape.
        win = window_from_bounds(*bounds_target, transform=ds.transform)
        arr = ds.read(
            1,
            window=win,
            out_shape=(height, width),
            boundless=True,
            fill_value=0,
            resampling=Resampling.bilinear,
        )
    return arr.astype("float32")


def _fetch_window(catalog, aoi: AOI, t_label: str, window) -> dict:
    item = _pick_scene(catalog, aoi, window)
    assets = item.assets
    # Reference grid from the 10 m NIR band (B08); fall back to first listed band.
    ref_band = "B08" if "B08" in assets else aoi.stac.bands[0]
    with rasterio.open(assets[ref_band].href) as ref:
        target_crs = ref.crs.to_string()
    minx, miny, maxx, maxy = transform_bounds("EPSG:4326", target_crs, *aoi.bbox)
    width = max(1, round((maxx - minx) / TARGET_RES_M))
    height = max(1, round((maxy - miny) / TARGET_RES_M))
    transform = from_bounds(minx, miny, maxx, maxy, width, height)

    bands: dict = {}
    for band in aoi.stac.bands:
        if band not in assets:
            log.warning("  band %s not in item assets, skipping", band)
            continue
        bands[band] = _read_band(assets[band].href, (minx, miny, maxx, maxy), target_crs, height, width)
    meta = {
        "stac_item_id": item.id,
        "datetime": item.properties.get("datetime"),
        "cloud_cover": item.properties.get("eo:cloud_cover"),
        "source": "planetary_computer/sentinel-2-l2a",
    }
    return save_window(aoi.name, t_label, bands, transform, target_crs, meta)


def main() -> int:
    aoi = get_aoi()
    settings = get_settings()
    ensure_bucket()
    log.info("Fetching Sentinel-2 bi-temporal pair for AOI '%s' %s", aoi.name, aoi.bbox)
    try:
        catalog = _open_catalog()
        _fetch_window(catalog, aoi, "t0", aoi.stac.t0)
        _fetch_window(catalog, aoi, "t1", aoi.stac.t1)
    except Exception as exc:  # network / PC outage
        if not settings.allow_offline_fallback:
            raise
        log.warning("STAC fetch failed (%s). ALLOW_OFFLINE_FALLBACK=1 → synthetic pair.", exc)
        from agrisentinel.seed import ensure_synthetic_s2

        ensure_synthetic_s2(aoi)
    log.info("Sentinel-2 ingestion complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
