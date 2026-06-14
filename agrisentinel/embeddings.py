"""Text embedders for the regulation RAG.

Two interchangeable backends behind one interface so the pipeline runs light by
default but can be upgraded without schema or code changes:

* ``tfidf-svd`` (default) — character n-gram TF-IDF + Truncated SVD (LSA),
  pure scikit-learn, no torch. Handles mixed Chinese/English legal text. It is
  **deterministic** given the same corpus and ``random_state`` (SVD components
  depend on Aᵀ·A, invariant to document order), so query-time encoding simply
  re-fits on the identical stored chunk corpus — no model artifact to serialise.
* ``sentence-transformers`` — multilingual MiniLM (requires the ``ml`` extra),
  stronger semantic recall. Stateless: re-loaded by name at query time.

Both emit L2-normalised float32 vectors of length ``EMBED_DIM`` (zero-padded if
the SVD rank is smaller), so pgvector cosine search is consistent across runs.
"""

from __future__ import annotations

import numpy as np

from agrisentinel.config import Settings, get_settings
from agrisentinel.logging import get_logger

log = get_logger(__name__)


def to_vector_literal(vec) -> str:
    """Render a vector as pgvector's text input form ``[v1,v2,...]``.

    Used with an explicit ``::vector`` cast so queries/inserts don't depend on a
    psycopg list/numpy dumper being registered (a plain list is otherwise sent as
    ``double precision[]``, which has no ``<=>`` operator)."""
    return "[" + ",".join(f"{float(x):.7g}" for x in vec) + "]"


def _l2_pad(mat: np.ndarray, dim: int) -> np.ndarray:
    mat = np.asarray(mat, dtype="float32")
    if mat.shape[1] < dim:
        mat = np.pad(mat, ((0, 0), (0, dim - mat.shape[1])))
    elif mat.shape[1] > dim:
        mat = mat[:, :dim]
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (mat / norms).astype("float32")


class TfidfSvdEmbedder:
    name = "tfidf-svd"

    def __init__(self, dim: int = 384):
        self.dim = dim
        self._vectorizer = None
        self._svd = None

    def fit(self, corpus: list[str]) -> TfidfSvdEmbedder:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4), min_df=1, max_features=60000
        )
        x = self._vectorizer.fit_transform(corpus)
        n_comp = max(1, min(self.dim, x.shape[1] - 1, max(1, x.shape[0] - 1)))
        self._svd = TruncatedSVD(n_components=n_comp, random_state=42)
        self._svd.fit(x)
        log.info(
            "Fitted TF-IDF+SVD on %d chunks → %d components (pad to %d).",
            x.shape[0], n_comp, self.dim,
        )
        return self

    def encode(self, texts: list[str]) -> np.ndarray:
        if self._vectorizer is None or self._svd is None:
            raise RuntimeError("TfidfSvdEmbedder used before fit().")
        x = self._vectorizer.transform(texts)
        z = self._svd.transform(x)
        return _l2_pad(z, self.dim)


class SentenceTransformerEmbedder:
    name = "sentence-transformers"

    def __init__(self, dim: int = 384, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.dim = dim
        self.model_name = model_name
        self._model = None

    def _ensure(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def fit(self, corpus: list[str]) -> SentenceTransformerEmbedder:  # stateless
        self._ensure()
        return self

    def encode(self, texts: list[str]) -> np.ndarray:
        vecs = self._ensure().encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return _l2_pad(np.asarray(vecs, dtype="float32"), self.dim)


def get_embedder(settings: Settings | None = None):
    """Construct a fresh (unfitted) embedder per settings."""
    s = settings or get_settings()
    if s.embedder == "sentence-transformers":
        return SentenceTransformerEmbedder(dim=s.embed_dim)
    return TfidfSvdEmbedder(dim=s.embed_dim)


def _load_chunk_corpus() -> list[str]:
    """All stored law-chunk texts in id order (the corpus the embeddings used)."""
    from agrisentinel.db import get_conn

    with get_conn() as conn:
        rows = conn.execute("SELECT content FROM law_chunks ORDER BY id;").fetchall()
    return [r[0] for r in rows]


def load_fitted_embedder(settings: Settings | None = None):
    """Return an embedder ready to encode queries in the same space as the stored
    chunk embeddings. For TF-IDF+SVD this re-fits on the stored corpus (cheap and
    deterministic); for sentence-transformers it just loads the model by name."""
    s = settings or get_settings()
    if s.embedder == "sentence-transformers":
        return SentenceTransformerEmbedder(dim=s.embed_dim).fit([])
    corpus = _load_chunk_corpus()
    if not corpus:
        raise RuntimeError("No law chunks found. Run `fetch-laws` first.")
    return TfidfSvdEmbedder(dim=s.embed_dim).fit(corpus)
