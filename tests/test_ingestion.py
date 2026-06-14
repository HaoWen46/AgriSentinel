"""Ingestion smoke tests that need neither network nor a database."""

from shapely import from_wkt

from agrisentinel.config import get_aoi
from ingestion.laws_fetch import build_chunks
from ingestion.parcels_load import synthetic_parcels


def test_synthetic_parcels_grid():
    aoi = get_aoi()
    rows = synthetic_parcels(aoi)
    assert len(rows) > 50
    farm = sum(1 for r in rows if r["is_farmland"])
    frac = farm / len(rows)
    # deterministic ~0.7 farmland fraction
    assert 0.55 < frac < 0.85
    # geometries are valid polygons inside roughly the AOI bbox
    g = from_wkt(rows[0]["wkt"])
    assert g.is_valid
    minx, miny, maxx, maxy = aoi.bbox
    assert minx - 0.01 <= g.centroid.x <= maxx + 0.01


def test_law_chunks_built_from_seed():
    aoi = get_aoi()
    chunks = build_chunks(aoi)
    assert len(chunks) >= 10
    titles = {c["law_title"] for c in chunks}
    assert "工廠管理輔導法" in titles
    assert "區域計畫法" in titles
    # every chunk carries provenance + non-empty content
    for c in chunks:
        assert c["pcode"] and c["content"].strip()
