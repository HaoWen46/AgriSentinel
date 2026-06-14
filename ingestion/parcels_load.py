"""Phase 1 — farmland parcels + zoning + 地號 into PostGIS.

Providers (set ``parcels.provider`` in the AOI config):

* ``synthetic`` (default) — a deterministic, reproducible parcel grid over the
  AOI. Clearly labelled ``source='synthetic'`` in the table and the report. This
  exists because the full NLSC vector cadastre (地籍 WFS) requires a
  government/academic application — itself a Component-3 data-acquisition point.
* ``geojson`` — load polygons from a local/remote GeoJSON (set ``parcels.path``).
* ``landuse`` — load a 國土利用現況調查 land-use clip (set ``parcels.path``).

Run: ``uv run python -m ingestion.parcels_load``.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from shapely.geometry import box, shape

from agrisentinel.config import AOI, get_aoi, get_settings, repo_root
from agrisentinel.db import get_conn
from agrisentinel.geo import WGS84, reproject_geom, wkt
from agrisentinel.logging import get_logger

log = get_logger(__name__)

_UPSERT = """
INSERT INTO parcels (parcel_id, aoi, landcode, sectname, sectcode, landuse_code,
                     is_farmland, source, geom)
VALUES (%(parcel_id)s, %(aoi)s, %(landcode)s, %(sectname)s, %(sectcode)s,
        %(landuse_code)s, %(is_farmland)s, %(source)s,
        ST_SetSRID(ST_GeomFromText(%(wkt)s), 4326))
ON CONFLICT (parcel_id) DO UPDATE SET
    is_farmland = EXCLUDED.is_farmland,
    landuse_code = EXCLUDED.landuse_code,
    geom = EXCLUDED.geom;
"""

# Land-use code prefixes considered agricultural (國土利用現況調查 / 編定 codes).
FARMLAND_KEYWORDS = ("農", "agric", "farm", "paddy", "crop")


def _deterministic_unit(seed: int, i: int, j: int) -> float:
    """Stable pseudo-random in [0,1) independent of PYTHONHASHSEED."""
    v = (seed * 73856093) ^ (i * 19349663) ^ (j * 83492791)
    return (v % 100000) / 100000.0


def synthetic_parcels(aoi: AOI) -> list[dict]:
    cfg = aoi.parcels.synthetic
    minx, miny, maxx, maxy = aoi.bbox
    # Work in metres: project the bbox corners to the working CRS.
    wminx, wminy = reproject_geom(box(minx, miny, maxx, maxy), WGS84, aoi.working_crs).bounds[:2]
    wmaxx, wmaxy = reproject_geom(box(minx, miny, maxx, maxy), WGS84, aoi.working_crs).bounds[2:]
    step = cfg.grid_m
    rows: list[dict] = []
    j = 0
    y = wminy
    while y < wmaxy:
        i = 0
        x = wminx
        while x < wmaxx:
            cell_w = box(x, y, min(x + step, wmaxx), min(y + step, wmaxy))
            cell_wgs = reproject_geom(cell_w, aoi.working_crs, WGS84)
            is_farm = _deterministic_unit(cfg.seed, i, j) < cfg.farmland_fraction
            rows.append(
                {
                    "parcel_id": f"{aoi.name}-{i:03d}-{j:03d}",
                    "aoi": aoi.name,
                    "landcode": f"SIM-{i:03d}{j:03d}",
                    "sectname": "示範段 (synthetic)",
                    "sectcode": "SIM",
                    "landuse_code": "農牧用地" if is_farm else "甲種建築用地",
                    "is_farmland": is_farm,
                    "source": "synthetic",
                    "wkt": wkt(cell_wgs),
                }
            )
            i += 1
            x += step
        j += 1
        y += step
    return rows


def _is_farmland(props: dict) -> bool:
    if "is_farmland" in props:
        return bool(props["is_farmland"])
    text = " ".join(str(props.get(k, "")) for k in ("landuse", "landuse_code", "編定", "use", "類別"))
    return any(k.lower() in text.lower() for k in FARMLAND_KEYWORDS)


def geojson_parcels(aoi: AOI, path_or_url: str) -> list[dict]:
    if path_or_url.startswith(("http://", "https://")):
        with httpx.Client(timeout=60.0) as client:
            fc = client.get(path_or_url).json()
    else:
        p = Path(path_or_url)
        if not p.is_absolute():
            p = repo_root() / p
        fc = json.loads(p.read_text(encoding="utf-8"))
    aoi_box = box(*aoi.bbox)
    rows: list[dict] = []
    for idx, feat in enumerate(fc.get("features", [])):
        geom = shape(feat["geometry"])
        if not geom.intersects(aoi_box):
            continue
        geom = geom.intersection(aoi_box)
        if geom.is_empty:
            continue
        props = feat.get("properties", {})
        rows.append(
            {
                "parcel_id": str(props.get("parcel_id") or props.get("landcode") or f"{aoi.name}-gj-{idx}"),
                "aoi": aoi.name,
                "landcode": props.get("landcode") or props.get("地號"),
                "sectname": props.get("sectname") or props.get("段名"),
                "sectcode": props.get("sectcode"),
                "landuse_code": props.get("landuse_code") or props.get("編定"),
                "is_farmland": _is_farmland(props),
                "source": aoi.parcels.provider,
                "wkt": wkt(geom),
            }
        )
    return rows


def upsert_parcels(rows: list[dict]) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.executemany(_UPSERT, rows)
    return len(rows)


def build_parcels(aoi: AOI) -> list[dict]:
    provider = aoi.parcels.provider
    if provider == "synthetic":
        return synthetic_parcels(aoi)
    if provider in ("geojson", "landuse"):
        if not aoi.parcels.path:
            raise ValueError(f"parcels.provider={provider} requires parcels.path")
        return geojson_parcels(aoi, aoi.parcels.path)
    raise ValueError(f"Unknown parcels.provider: {provider}")


def main() -> int:
    aoi = get_aoi()
    settings = get_settings()
    try:
        rows = build_parcels(aoi)
    except Exception as exc:
        if not settings.allow_offline_fallback:
            raise
        log.warning("Parcel build failed (%s) → synthetic fallback.", exc)
        rows = synthetic_parcels(aoi)
    n = upsert_parcels(rows)
    farmland = sum(1 for r in rows if r["is_farmland"])
    log.info("Loaded %d parcels (%d farmland) via '%s'.", n, farmland, aoi.parcels.provider)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
