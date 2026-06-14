"""Offline sample data — keeps the whole pipeline runnable without network.

Generates a deterministic synthetic Sentinel-2 bi-temporal pair (vegetated
farmland in ``t0``; several new "buildings" stamped in ``t1`` where NDBI rises
and NDVI falls together) plus a small Disfactory-shaped label set, then loads
parcels and the statute RAG. Doubles as the fallback for ``stac_fetch`` /
``labels_fetch`` when upstream sources are unreachable.

Run the full offline ingestion with: ``uv run python -m agrisentinel.seed``.
"""

from __future__ import annotations

import numpy as np
from rasterio.transform import from_bounds
from shapely.geometry import box

from agrisentinel.config import AOI, get_aoi
from agrisentinel.geo import WGS84, reproject_geom
from agrisentinel.logging import get_logger
from agrisentinel.raster import save_window
from agrisentinel.storage import ensure_bucket

log = get_logger(__name__)

RES_M = 10.0

# Reflectance signatures (any consistent scale; only band ratios matter).
_VEG = {"B02": 0.04, "B03": 0.07, "B04": 0.06, "B08": 0.35, "B11": 0.20, "B12": 0.18}
_BUILDING = {"B02": 0.18, "B03": 0.19, "B04": 0.20, "B08": 0.22, "B11": 0.34, "B12": 0.30}

# New-construction patch centres (lon, lat) inside the AOI bbox.
_PATCHES = [
    (120.5000, 24.1200),
    (120.5100, 24.1150),
    (120.4900, 24.1300),
    (120.5200, 24.1000),
    (120.4950, 24.1050),
    (120.5150, 24.1250),
]
# Sample labels: 4 coincide with patches (true positives), 1 is a missed factory
# with no detectable patch (false negative). The 2 patches without a label act as
# false positives — so precision and recall are both strictly < 1.
_LABEL_POINTS = _PATCHES[:4] + [(120.4750, 24.1400)]


def _grid(aoi: AOI):
    bounds = reproject_geom(box(*aoi.bbox), WGS84, aoi.working_crs).bounds
    minx, miny, maxx, maxy = bounds
    width = max(8, round((maxx - minx) / RES_M))
    height = max(8, round((maxy - miny) / RES_M))
    transform = from_bounds(minx, miny, maxx, maxy, width, height)
    return transform, height, width, bounds


def _project_point(lon, lat, aoi: AOI):
    from shapely.geometry import Point

    p = reproject_geom(Point(lon, lat), WGS84, aoi.working_crs)
    return p.x, p.y


def _lonlat_to_px(lon, lat, aoi: AOI, transform):
    x, y = _project_point(lon, lat, aoi)
    col = int((x - transform.c) / transform.a)
    row = int((y - transform.f) / transform.e)
    return row, col


def ensure_synthetic_s2(aoi: AOI) -> None:
    ensure_bucket()
    transform, height, width, _ = _grid(aoi)
    rng = np.random.default_rng(aoi.parcels.synthetic.seed)

    def scene(buildings: bool) -> dict[str, np.ndarray]:
        bands = {
            b: np.full((height, width), val, dtype="float32") + rng.normal(0, 0.01, (height, width)).astype("float32")
            for b, val in _VEG.items()
        }
        if buildings:
            half_px = max(3, int(30 / RES_M))  # ~60 m square
            for lon, lat in _PATCHES:
                r, c = _lonlat_to_px(lon, lat, aoi, transform)
                r0, r1 = max(0, r - half_px), min(height, r + half_px)
                c0, c1 = max(0, c - half_px), min(width, c + half_px)
                if r0 >= r1 or c0 >= c1:
                    continue
                for b, val in _BUILDING.items():
                    bands[b][r0:r1, c0:c1] = val + rng.normal(0, 0.005, (r1 - r0, c1 - c0)).astype("float32")
        return {b: np.clip(a, 0, 1) for b, a in bands.items()}

    save_window(aoi.name, "t0", scene(False), transform, aoi.working_crs,
                {"source": "synthetic", "datetime": "2020-01-15T00:00:00Z", "cloud_cover": 0})
    save_window(aoi.name, "t1", scene(True), transform, aoi.working_crs,
                {"source": "synthetic", "datetime": "2024-12-15T00:00:00Z", "cloud_cover": 0})
    log.info("Wrote synthetic Sentinel-2 pair (%dx%d) with %d new-build patches.",
             height, width, len(_PATCHES))


def sample_labels(aoi: AOI) -> list[dict]:
    out = []
    for i, (lon, lat) in enumerate(_LABEL_POINTS):
        out.append(
            {
                "id": f"sample-{aoi.name}-{i}",
                "display_number": 90000 + i,
                "name": "",
                "landcode": f"SAMPLE-{i:03d}",
                "townname": f"{aoi.county}{aoi.township}",
                "sectname": "示範段 (sample)",
                "sectcode": "SMP",
                "source": "sample",
                "factory_type": None,
                "status": "A",
                "reported_at": "2024-12-15T00:00:00Z",
                "lng": lon,
                "lat": lat,
            }
        )
    return out


def main() -> int:
    aoi = get_aoi()
    log.info("Seeding offline sample data for AOI '%s'.", aoi.name)
    ensure_synthetic_s2(aoi)

    from ingestion.labels_fetch import upsert_labels
    from ingestion.laws_fetch import main as fetch_laws
    from ingestion.parcels_load import synthetic_parcels, upsert_parcels

    n_labels = upsert_labels(aoi.name, sample_labels(aoi))
    n_parcels = upsert_parcels(synthetic_parcels(aoi))
    fetch_laws()
    log.info("Seed complete: %d labels, %d parcels, statutes embedded.", n_labels, n_parcels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
