"""Phase 3 — spatial join: detections × farmland parcels (PostGIS).

A change polygon is only a *candidate violation* once it sits on agricultural
land. This joins detections to parcels with ``ST_Intersects``, keeps only
overlaps on farmland, attaches the 地號 (landcode) and 段, finds the nearest
Disfactory label for each, and ranks by confidence into ``flagged_parcels`` —
the ranked worklist the dossier agent consumes. Idempotent per run.

Run: ``uv run python -m processing.zoning_join``.
"""

from __future__ import annotations

from agrisentinel.db import get_conn
from agrisentinel.logging import get_logger
from agrisentinel.runs import resolve_run_id

log = get_logger(__name__)

_JOIN = """
INSERT INTO flagged_parcels (run_id, detection_id, parcel_id, aoi, landcode, sectname,
                             is_farmland, overlap_area_m2, confidence, geom)
SELECT d.run_id, d.id, p.parcel_id, d.aoi, p.landcode, p.sectname, p.is_farmland,
       ST_Area(ST_Transform(ST_Intersection(d.geom, p.geom), 3826)) AS overlap_area_m2,
       d.confidence, d.geom
FROM detections d
JOIN parcels p
  ON p.aoi = d.aoi AND p.is_farmland = TRUE AND ST_Intersects(d.geom, p.geom)
WHERE d.run_id = %(run_id)s;
"""

_NEAREST = """
UPDATE flagged_parcels f SET
  matched_label_id = (
    SELECT l.id FROM labels l WHERE l.aoi = f.aoi ORDER BY f.geom <-> l.geom LIMIT 1),
  distance_to_label_m = (
    SELECT ST_Distance(ST_Transform(f.geom, 3826), ST_Transform(l.geom, 3826))
    FROM labels l WHERE l.aoi = f.aoi ORDER BY f.geom <-> l.geom LIMIT 1)
WHERE f.run_id = %(run_id)s;
"""

_RANK = """
WITH ranked AS (
  SELECT id, row_number() OVER (ORDER BY confidence DESC, overlap_area_m2 DESC) AS rn
  FROM flagged_parcels WHERE run_id = %(run_id)s)
UPDATE flagged_parcels f SET rank = r.rn FROM ranked r WHERE f.id = r.id;
"""


def main() -> int:
    run_id = resolve_run_id()
    if not run_id:
        raise RuntimeError("No detection run found. Run `detect` first.")
    log.info("Zoning join for run '%s'.", run_id)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM flagged_parcels WHERE run_id = %(run_id)s;", {"run_id": run_id})
        cur.execute(_JOIN, {"run_id": run_id})
        cur.execute(_NEAREST, {"run_id": run_id})
        cur.execute(_RANK, {"run_id": run_id})
        n = cur.execute(
            "SELECT count(*) FROM flagged_parcels WHERE run_id = %(run_id)s;", {"run_id": run_id}
        ).fetchone()[0]
        ndet = cur.execute(
            "SELECT count(DISTINCT detection_id) FROM flagged_parcels WHERE run_id=%(run_id)s;",
            {"run_id": run_id},
        ).fetchone()[0]
    log.info("Flagged %d parcel-overlaps on farmland (%d distinct detections) for run '%s'.",
             n, ndet, run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
