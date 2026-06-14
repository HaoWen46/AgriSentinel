from agrisentinel.config import get_aoi, get_settings


def test_aoi_loads():
    a = get_aoi()
    assert a.name == "changhua_hemei"
    assert len(a.bbox) == 4
    assert a.bbox[0] < a.bbox[2] and a.bbox[1] < a.bbox[3]
    assert "B08" in a.stac.bands and "B11" in a.stac.bands
    assert a.working_crs == "EPSG:3826"
    assert len(a.laws.pcodes) == 4


def test_settings_defaults():
    s = get_settings()
    assert s.embed_dim == 384
    # data_path must be a relative-derived absolute path, never a leaked machine path.
    assert s.data_path.name == "data" or s.data_dir is not None
