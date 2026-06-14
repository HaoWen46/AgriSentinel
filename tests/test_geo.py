import numpy as np
from rasterio.transform import from_bounds
from shapely.geometry import box

from agrisentinel.geo import WGS84, area_m2, mask_to_polygons, reproject_geom


def test_area_of_known_box():
    # ~0.01° square near Changhua; area in m² should be on the order of 1e6.
    poly = box(120.50, 24.10, 120.51, 24.11)
    a = area_m2(poly, "EPSG:3826")
    assert 5e5 < a < 2e6


def test_reproject_roundtrip():
    poly = box(120.50, 24.10, 120.51, 24.11)
    there = reproject_geom(poly, WGS84, "EPSG:3826")
    back = reproject_geom(there, "EPSG:3826", WGS84)
    assert back.bounds[0] == np.float64(back.bounds[0])
    assert abs(back.bounds[0] - poly.bounds[0]) < 1e-6


def test_mask_to_polygons():
    # 50x50 grid in EPSG:3826 at 10 m; flag a 10x10 block (10000 m²).
    minx, miny = 200000, 2600000
    transform = from_bounds(minx, miny, minx + 500, miny + 500, 50, 50)
    mask = np.zeros((50, 50), dtype=bool)
    mask[10:20, 10:20] = True
    polys = mask_to_polygons(mask, transform, "EPSG:3826", working_crs="EPSG:3826", min_area_m2=400)
    assert len(polys) == 1
    poly, area = polys[0]
    assert 8000 < area < 12000
