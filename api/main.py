"""Phase 5/6 — FastAPI delivery: GeoJSON layers, dossiers, imagery, metrics, SSE.

Serves the Leaflet dashboard at ``/`` and a small JSON/GeoJSON API the dashboard
consumes. Self-initialises the schema on startup. Imagery endpoints render
before/after RGB composites straight from the MinIO COGs.

Run: ``uv run python -m agrisentinel.cli serve`` (or ``uvicorn api.main:app``).
"""

from __future__ import annotations

import json
import uuid

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from psycopg.rows import dict_row

from agrisentinel.config import get_aoi, repo_root
from agrisentinel.db import get_conn
from agrisentinel.logging import get_logger
from agrisentinel.runs import resolve_run_id

log = get_logger(__name__)
app = FastAPI(title="AgriSentinel", version="0.1.0")
DASHBOARD = repo_root() / "dashboard" / "index.html"


@app.on_event("startup")
def _startup() -> None:
    try:
        from agrisentinel.db import ensure_extensions, run_sql_file

        ensure_extensions()
        run_sql_file("scripts/init_db.sql")
        log.info("API startup: schema ensured.")
    except Exception as exc:  # API still boots; data endpoints will 503 until DB is up
        log.warning("API startup schema init deferred: %s", exc)


def _fc(rows: list[dict], geojson_key: str = "gj") -> dict:
    feats = []
    for r in rows:
        geom = r.pop(geojson_key)
        feats.append(
            {"type": "Feature", "geometry": json.loads(geom) if geom else None, "properties": r}
        )
    return {"type": "FeatureCollection", "features": feats}


@app.get("/", include_in_schema=False)
def index():
    if DASHBOARD.exists():
        return FileResponse(str(DASHBOARD))
    return JSONResponse({"service": "agrisentinel", "dashboard": "not found"})


@app.get("/api/health")
def health():
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1;")
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"db unavailable: {exc}") from exc


@app.get("/api/aoi")
def aoi_info():
    a = get_aoi()
    return {
        "name": a.name,
        "display_name": a.display_name,
        "county": a.county,
        "township": a.township,
        "bbox": a.bbox,
        "center": {"lon": a.center.lon, "lat": a.center.lat},
    }


@app.get("/api/runs")
def runs():
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT d.run_id,
                   max(d.created_at)::text AS created_at,
                   count(*) AS n_detections,
                   (SELECT count(*) FROM flagged_parcels f WHERE f.run_id=d.run_id) AS n_flagged,
                   (SELECT count(*) FROM dossiers ds WHERE ds.run_id=d.run_id) AS n_dossiers
            FROM detections d GROUP BY d.run_id ORDER BY max(d.created_at) DESC;
            """
        ).fetchall()
    return {"runs": rows, "latest": rows[0]["run_id"] if rows else None}


@app.get("/api/parcels")
def parcels(farmland_only: bool = False, limit: int = Query(8000, le=20000)):
    a = get_aoi()
    where = "WHERE aoi=%s" + (" AND is_farmland=TRUE" if farmland_only else "")
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            f"""SELECT parcel_id, landcode, sectname, is_farmland, source,
                       ST_AsGeoJSON(geom) AS gj
                FROM parcels {where} LIMIT %s;""",
            (a.name, limit),
        ).fetchall()
    return _fc(rows)


@app.get("/api/labels")
def labels():
    a = get_aoi()
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """SELECT id, display_number, landcode, townname, sectname, status,
                      reported_at::text AS reported_at, source, ST_AsGeoJSON(geom) AS gj
               FROM labels WHERE aoi=%s;""",
            (a.name,),
        ).fetchall()
    return _fc(rows)


@app.get("/api/detections")
def detections(run_id: str | None = None):
    run_id = run_id or resolve_run_id()
    if not run_id:
        return _fc([])
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """SELECT id, run_id, detector, t0_date, t1_date, ndbi_delta, ndvi_drop,
                      confidence, area_m2, ST_AsGeoJSON(geom) AS gj
               FROM detections WHERE run_id=%s;""",
            (run_id,),
        ).fetchall()
    return _fc(rows)


@app.get("/api/flagged")
def flagged(run_id: str | None = None):
    run_id = run_id or resolve_run_id()
    if not run_id:
        return _fc([])
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT f.id AS flagged_id, f.detection_id, f.parcel_id, f.landcode, f.sectname,
                   f.is_farmland, f.overlap_area_m2, f.confidence, f.rank,
                   f.matched_label_id, f.distance_to_label_m,
                   (ds.id IS NOT NULL) AS has_dossier,
                   ST_AsGeoJSON(f.geom) AS gj
            FROM flagged_parcels f
            LEFT JOIN dossiers ds ON ds.flagged_id = f.id
            WHERE f.run_id=%s ORDER BY f.rank NULLS LAST;
            """,
            (run_id,),
        ).fetchall()
    return _fc(rows)


@app.get("/api/metrics")
def metrics(run_id: str | None = None):
    run_id = run_id or resolve_run_id()
    if not run_id:
        return {}
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            "SELECT payload FROM metrics WHERE run_id=%s ORDER BY created_at DESC LIMIT 1;",
            (run_id,),
        ).fetchone()
    return row["payload"] if row else {}


@app.get("/api/dossiers")
def dossier_list(run_id: str | None = None):
    run_id = run_id or resolve_run_id()
    if not run_id:
        return {"dossiers": []}
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT ds.flagged_id, ds.parcel_id, ds.landcode, ds.model, ds.confidence,
                   ds.violated_law, f.rank
            FROM dossiers ds JOIN flagged_parcels f ON f.id = ds.flagged_id
            WHERE ds.run_id=%s ORDER BY f.rank NULLS LAST;
            """,
            (run_id,),
        ).fetchall()
    return {"dossiers": rows}


@app.get("/api/dossiers/{flagged_id}")
def dossier(flagged_id: int):
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """SELECT flagged_id, parcel_id, landcode, model, confidence, violated_law,
                      recommended_action, dossier_md, dossier_json
               FROM dossiers WHERE flagged_id=%s;""",
            (flagged_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="dossier not found")
    return row


def _stretch(channel: np.ndarray) -> np.ndarray:
    finite = channel[np.isfinite(channel)]
    if finite.size == 0:
        return np.zeros_like(channel, dtype="uint8")
    lo, hi = np.percentile(finite, [2, 98])
    if hi <= lo:
        hi = lo + 1e-6
    return np.clip((channel - lo) / (hi - lo) * 255, 0, 255).astype("uint8")


@app.get("/api/imagery/{t_label}.png")
def imagery(
    t_label: str,
    minx: float | None = None,
    miny: float | None = None,
    maxx: float | None = None,
    maxy: float | None = None,
):
    if t_label not in ("t0", "t1"):
        raise HTTPException(status_code=400, detail="t_label must be t0 or t1")
    from rasterio.io import MemoryFile
    from rasterio.warp import transform_bounds

    from agrisentinel.raster import load_window, window_exists

    a = get_aoi()
    if not window_exists(a.name, t_label):
        raise HTTPException(status_code=404, detail=f"no imagery for {t_label}; run ingest/seed")
    bands, transform, crs, _ = load_window(a.name, t_label)
    rgb_bands = [bands.get(b) for b in ("B04", "B03", "B02")]
    if any(x is None for x in rgb_bands):
        first = next(iter(bands.values()))
        rgb_bands = [first, first, first]
    rgb = np.stack(rgb_bands)  # (3, H, W)

    if None not in (minx, miny, maxx, maxy):
        bx0, by0, bx1, by1 = transform_bounds("EPSG:4326", crs, minx, miny, maxx, maxy)
        c0 = max(0, int((bx0 - transform.c) / transform.a))
        c1 = min(rgb.shape[2], int((bx1 - transform.c) / transform.a))
        r0 = max(0, int((by1 - transform.f) / transform.e))
        r1 = min(rgb.shape[1], int((by0 - transform.f) / transform.e))
        if r1 > r0 and c1 > c0:
            rgb = rgb[:, r0:r1, c0:c1]

    out = np.stack([_stretch(rgb[i]) for i in range(3)])
    h, w = out.shape[1], out.shape[2]
    with MemoryFile() as mem:
        with mem.open(driver="PNG", height=h, width=w, count=3, dtype="uint8") as ds:
            ds.write(out)
        png = mem.read()
    return Response(content=png, media_type="image/png")


@app.get("/api/stream")
def stream(request: Request):
    """Server-Sent Events: forward pipeline events to the dashboard."""

    def gen():
        from api.stream import consume_events

        yield "retry: 5000\n\n"
        try:
            for event in consume_events(group_id=f"sse-{uuid.uuid4().hex[:8]}"):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            yield f": stream unavailable ({exc})\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
