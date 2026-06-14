import numpy as np

from agrisentinel.embeddings import TfidfSvdEmbedder


def test_tfidf_svd_shape_and_norm():
    corpus = [
        "工廠管理輔導法 第28-1條 新增建未登記工廠 停止供電供水 拆除",
        "區域計畫法 第21條 違反非都市土地使用管制 罰鍰 拆除地上物",
        "農業發展條例 農地農用 農業用地 定義",
        "non-urban land use control regulations agricultural land factory prohibited",
    ]
    emb = TfidfSvdEmbedder(dim=384).fit(corpus)
    vecs = emb.encode(corpus)
    assert vecs.shape == (4, 384)
    norms = np.linalg.norm(vecs, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4)


def test_tfidf_svd_determinism():
    corpus = ["農地 工廠 違規", "區域計畫法 罰則", "Sentinel-2 change detection"]
    a = TfidfSvdEmbedder(dim=128).fit(corpus).encode(corpus)
    b = TfidfSvdEmbedder(dim=128).fit(corpus).encode(corpus)
    # Re-fitting on the same corpus must reproduce the same projection (query-time
    # encoding relies on this, since the fitted model is not persisted).
    assert np.allclose(a, b, atol=1e-5)
