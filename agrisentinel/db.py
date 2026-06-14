"""PostGIS (+pgvector) access helpers built on psycopg 3.

Connections register the pgvector type adapter when the extension is present, so
``vector`` columns round-trip as Python lists / numpy arrays transparently.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

import psycopg
from tenacity import retry, stop_after_attempt, wait_fixed

from agrisentinel.config import get_settings, repo_root
from agrisentinel.logging import get_logger

log = get_logger(__name__)


def _register_pgvector(conn: psycopg.Connection) -> None:
    try:
        from pgvector.psycopg import register_vector

        register_vector(conn)
    except Exception as exc:  # extension may not be created yet (e.g. first init)
        log.debug("pgvector type not registered yet: %s", exc)


@retry(stop=stop_after_attempt(20), wait=wait_fixed(2), reraise=True)
def connect(*, autocommit: bool = True) -> psycopg.Connection:
    """Open a connection, retrying while the database boots (docker compose)."""
    settings = get_settings()
    conn = psycopg.connect(settings.database_url, autocommit=autocommit)
    _register_pgvector(conn)
    return conn


@contextlib.contextmanager
def get_conn(*, autocommit: bool = True) -> Iterator[psycopg.Connection]:
    conn = connect(autocommit=autocommit)
    try:
        yield conn
    finally:
        conn.close()


def ensure_extensions() -> None:
    """Create PostGIS + pgvector extensions (idempotent)."""
    with get_conn() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        _register_pgvector(conn)
    log.info("PostGIS + pgvector extensions ensured.")


def run_sql_file(path: str | Path) -> None:
    """Execute a .sql file (used for schema init)."""
    p = Path(path)
    if not p.is_absolute():
        p = repo_root() / p
    sql = p.read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.execute(sql)
    log.info("Applied SQL file: %s", p.name)


def table_count(table: str) -> int:
    """Row count for a table (0 if it does not exist)."""
    with get_conn() as conn:
        try:
            row = conn.execute(f"SELECT count(*) FROM {table};").fetchone()
            return int(row[0]) if row else 0
        except psycopg.Error:
            return 0
