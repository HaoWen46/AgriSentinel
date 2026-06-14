"""Phase 1 — Disfactory known-factory labels (the evaluation ground truth).

Disfactory's public API returns reported suspected-illegal factories within a
radius of a point: ``GET /api/factories?range=<km>&lng=<lon>&lat=<lat>``. Each
record already carries the cadastral number (地號 = ``landcode``) and 段
(``sectname``/``sectcode``). We fetch around the AOI centre, clip precisely to
the bbox, and upsert into PostGIS as the label set for precision/recall.

Data © Disfactory contributors (農地違章工廠回報系統貢獻者), CC BY 4.0.
Run: ``uv run python -m ingestion.labels_fetch``.
"""

from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from agrisentinel.config import AOI, get_aoi, get_settings
from agrisentinel.db import get_conn
from agrisentinel.logging import get_logger

log = get_logger(__name__)

DISFACTORY_API = "https://api.disfactory.tw/api/factories"

_UPSERT = """
INSERT INTO labels (id, aoi, display_number, name, landcode, townname, sectname,
                    sectcode, source, factory_type, status, reported_at, geom)
VALUES (%(id)s, %(aoi)s, %(display_number)s, %(name)s, %(landcode)s, %(townname)s,
        %(sectname)s, %(sectcode)s, %(source)s, %(factory_type)s, %(status)s,
        %(reported_at)s::timestamptz,
        ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326))
ON CONFLICT (id) DO UPDATE SET
    display_number = EXCLUDED.display_number,
    name = EXCLUDED.name,
    landcode = EXCLUDED.landcode,
    status = EXCLUDED.status,
    reported_at = EXCLUDED.reported_at,
    geom = EXCLUDED.geom;
"""


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, max=20), reraise=True)
def _query(range_km: float, lon: float, lat: float) -> list[dict]:
    params = {"range": range_km, "lng": lon, "lat": lat}
    with httpx.Client(timeout=40.0) as client:
        resp = client.get(DISFACTORY_API, params=params)
        resp.raise_for_status()
        return resp.json()


def fetch_labels(aoi: AOI) -> list[dict]:
    """Fetch (shrinking the radius if the API rejects a large one) and clip to bbox."""
    minx, miny, maxx, maxy = aoi.bbox
    for rng in sorted({aoi.disfactory_range_km, 5, 3, 1}, reverse=True):
        if rng > aoi.disfactory_range_km:
            continue
        try:
            raw = _query(rng, aoi.center.lon, aoi.center.lat)
        except Exception as exc:
            log.warning("Disfactory query range=%s failed: %s", rng, exc)
            continue
        in_bbox = [
            r
            for r in raw
            if r.get("lng") is not None
            and minx <= r["lng"] <= maxx
            and miny <= r["lat"] <= maxy
        ]
        log.info("Disfactory range=%skm → %d records, %d inside bbox", rng, len(raw), len(in_bbox))
        return in_bbox
    return []


def upsert_labels(aoi_name: str, records: list[dict]) -> int:
    rows = [
        {
            "id": r["id"],
            "aoi": aoi_name,
            "display_number": r.get("display_number"),
            "name": (r.get("name") or "").strip() or None,
            "landcode": r.get("landcode"),
            "townname": r.get("townname"),
            "sectname": r.get("sectname"),
            "sectcode": r.get("sectcode"),
            "source": r.get("source"),
            "factory_type": r.get("factory_type"),
            "status": r.get("status"),
            "reported_at": r.get("reported_at"),
            "lng": r["lng"],
            "lat": r["lat"],
        }
        for r in records
    ]
    with get_conn() as conn, conn.cursor() as cur:
        cur.executemany(_UPSERT, rows)
    return len(rows)


def main() -> int:
    aoi = get_aoi()
    settings = get_settings()
    try:
        records = fetch_labels(aoi)
        if not records:
            raise RuntimeError("Disfactory returned no in-bbox records.")
    except Exception as exc:
        if not settings.allow_offline_fallback:
            raise
        log.warning("Label fetch failed (%s). ALLOW_OFFLINE_FALLBACK=1 → sample labels.", exc)
        from agrisentinel.seed import sample_labels

        records = sample_labels(aoi)
    n = upsert_labels(aoi.name, records)
    log.info("Upserted %d Disfactory labels for AOI '%s'.", n, aoi.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
