import numpy as np
from rasterio.transform import from_bounds

from processing.change_detect import _binary_open, ndbi, ndvi
from processing.spark_tiles import compute_tiles, detect_in_window


def test_ndvi_ndbi_math():
    bands = {
        "B04": np.array([[0.06]]), "B08": np.array([[0.35]]),
        "B11": np.array([[0.20]]),
    }
    nd = ndvi(bands)[0, 0]
    nb = ndbi(bands)[0, 0]
    assert abs(nd - (0.29 / 0.41)) < 1e-6   # vegetation: high NDVI
    assert nb < 0                            # vegetation: negative NDBI


def test_binary_open_removes_speckle():
    m = np.zeros((10, 10), dtype=bool)
    m[5, 5] = True            # lone speckle pixel
    m[1:5, 1:5] = True        # solid block survives
    out = _binary_open(m, 1)
    assert not out[5, 5]
    assert out[2, 2]


def test_detect_in_window_finds_block():
    minx, miny = 200000, 2600000
    transform = from_bounds(minx, miny, minx + 500, miny + 500, 50, 50)
    delta = np.zeros((50, 50), dtype="float32")
    drop = np.zeros((50, 50), dtype="float32")
    delta[10:20, 10:20] = 0.25   # NDBI rise
    drop[10:20, 10:20] = 0.40    # NDVI fall
    cfg = {"ndbi_delta_min": 0.06, "ndvi_drop_min": 0.12, "min_area_m2": 400}
    dets = detect_in_window(delta, drop, transform, "EPSG:3826", "EPSG:3826", cfg)
    assert len(dets) == 1
    d = dets[0]
    assert d["area_m2"] > 8000
    assert d["confidence"] > 0.5
    assert d["wkt"].startswith("POLYGON")


def test_compute_tiles_covers_grid():
    tiles = compute_tiles(100, 80, 32)
    assert tiles[0] == (0, 32, 0, 32)
    # union of tiles must cover the whole array
    covered = np.zeros((100, 80), dtype=bool)
    for r0, r1, c0, c1 in tiles:
        covered[r0:r1, c0:c1] = True
    assert covered.all()
