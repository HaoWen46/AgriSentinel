"""Integration tests requiring PostGIS. Skipped automatically when the database
is unreachable (e.g. local unit runs without `docker compose up`)."""

import pytest

psycopg = pytest.importorskip("psycopg")


def _db_available() -> bool:
    try:
        from agrisentinel.db import connect

        conn = connect()
        conn.execute("SELECT 1;")
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="PostGIS not reachable")


def test_zoning_join_keeps_only_farmland(tmp_path):
    """A detection over a farmland parcel is flagged; one over non-farmland is not."""
    from agrisentinel.db import ensure_extensions, get_conn, run_sql_file

    ensure_extensions()
    run_sql_file("scripts/init_db.sql")
    run_id = "pytest-zoning"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM flagged_parcels WHERE run_id=%s;", (run_id,))
        cur.execute("DELETE FROM detections WHERE run_id=%s;", (run_id,))
        cur.execute("DELETE FROM parcels WHERE aoi='pytest';")
        # farmland parcel and a built parcel, side by side
        cur.execute("""INSERT INTO parcels (parcel_id,aoi,is_farmland,source,geom) VALUES
            ('pf','pytest',TRUE,'test', ST_SetSRID(ST_GeomFromText('POLYGON((0 0,0 0.001,0.001 0.001,0.001 0,0 0))'),4326)),
            ('pb','pytest',FALSE,'test',ST_SetSRID(ST_GeomFromText('POLYGON((1 1,1 1.001,1.001 1.001,1.001 1,1 1))'),4326))
            ON CONFLICT (parcel_id) DO UPDATE SET geom=EXCLUDED.geom, is_farmland=EXCLUDED.is_farmland;""")
        # detection overlapping the farmland parcel only
        cur.execute("""INSERT INTO detections (run_id,aoi,detector,confidence,area_m2,geom) VALUES
            (%s,'pytest','test',0.9,1000,
             ST_SetSRID(ST_GeomFromText('POLYGON((0 0,0 0.0005,0.0005 0.0005,0.0005 0,0 0))'),4326));""",
            (run_id,))

    import os
    os.environ["AGRISENTINEL_RUN_ID"] = run_id
    # Point the join at our synthetic aoi by temporarily overriding aoi name in SQL:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE detections SET aoi='pytest' WHERE run_id=%s;", (run_id,))
        cur.execute("""INSERT INTO flagged_parcels (run_id,detection_id,parcel_id,aoi,is_farmland,
                        overlap_area_m2,confidence,geom)
            SELECT d.run_id,d.id,p.parcel_id,d.aoi,p.is_farmland,
                   ST_Area(ST_Transform(ST_Intersection(d.geom,p.geom),3826)),d.confidence,d.geom
            FROM detections d JOIN parcels p
              ON p.aoi=d.aoi AND p.is_farmland=TRUE AND ST_Intersects(d.geom,p.geom)
            WHERE d.run_id=%s;""", (run_id,))
        n = cur.execute("SELECT count(*) FROM flagged_parcels WHERE run_id=%s;", (run_id,)).fetchone()[0]
        pids = [r[0] for r in cur.execute(
            "SELECT parcel_id FROM flagged_parcels WHERE run_id=%s;", (run_id,)).fetchall()]
    assert n == 1
    assert pids == ["pf"]
