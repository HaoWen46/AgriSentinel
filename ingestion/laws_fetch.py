"""Phase 4 — statutes → chunk → embed → pgvector (the dossier RAG substrate).

Loads the curated statute corpus under ``data/laws_seed/`` (excerpts from
全國法規資料庫 / MOJ open data, cited per file), splits each article into
overlapping chunks, embeds them with the configured embedder, and upserts into
the ``law_chunks`` pgvector table. Idempotent: chunks for the configured PCodes
are rebuilt on each run.

The corpus is bundled rather than scraped live because the MOJ Open API only
serves a full bulk dump (per-PCode requests are ignored); bundling keeps the RAG
reproducible offline. Point ``laws.pcodes`` at other statutes to extend it.

Run: ``uv run python -m ingestion.laws_fetch``.
"""

from __future__ import annotations

import json

from agrisentinel.config import AOI, get_aoi, get_settings, repo_root
from agrisentinel.db import get_conn
from agrisentinel.embeddings import get_embedder, to_vector_literal
from agrisentinel.logging import get_logger

log = get_logger(__name__)

SEED_DIR = repo_root() / "data" / "laws_seed"


def _chunk(text: str, size: int, overlap: int) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text]
    out, start = [], 0
    step = max(1, size - overlap)
    while start < len(text):
        out.append(text[start : start + size])
        start += step
    return out


def load_seed(pcode: str) -> dict | None:
    p = SEED_DIR / f"{pcode}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def build_chunks(aoi: AOI) -> list[dict]:
    chunks: list[dict] = []
    for ref in aoi.laws.pcodes:
        seed = load_seed(ref.pcode)
        if seed is None:
            log.warning("No seed corpus for %s (%s); skipping.", ref.pcode, ref.title)
            continue
        idx = 0
        for art in seed.get("articles", []):
            body = f"{seed['title']} {art.get('article_no', '')}：{art['text']}"
            for piece in _chunk(body, aoi.laws.chunk_chars, aoi.laws.chunk_overlap):
                chunks.append(
                    {
                        "pcode": ref.pcode,
                        "law_title": seed["title"],
                        "article_no": art.get("article_no"),
                        "chunk_index": idx,
                        "content": piece,
                    }
                )
                idx += 1
    return chunks


def main() -> int:
    aoi = get_aoi()
    settings = get_settings()
    chunks = build_chunks(aoi)
    if not chunks:
        raise RuntimeError(f"No law chunks built. Check {SEED_DIR}.")

    texts = [c["content"] for c in chunks]
    embedder = get_embedder(settings)
    embedder.fit(texts)
    vectors = embedder.encode(texts)
    log.info("Embedded %d chunks with '%s' (dim=%d).", len(chunks), embedder.name, vectors.shape[1])

    pcodes = sorted({c["pcode"] for c in chunks})
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM law_chunks WHERE pcode = ANY(%s);", (pcodes,))
        for c, vec in zip(chunks, vectors, strict=True):
            cur.execute(
                """
                INSERT INTO law_chunks (pcode, law_title, article_no, chunk_index, content, embedding)
                VALUES (%s, %s, %s, %s, %s, %s::vector)
                ON CONFLICT (pcode, chunk_index) DO UPDATE SET
                    content = EXCLUDED.content, embedding = EXCLUDED.embedding;
                """,
                (c["pcode"], c["law_title"], c["article_no"], c["chunk_index"], c["content"],
                 to_vector_literal(vec)),
            )
    log.info("Stored %d law chunks across %d statutes into pgvector.", len(chunks), len(pcodes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
