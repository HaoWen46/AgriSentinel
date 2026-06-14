"""Unified CLI: ``uv run agrisentinel <command>`` (or ``python -m agrisentinel.cli``).

Thin dispatcher — each subcommand defers to the relevant layer module so heavy
dependencies are only imported when actually used. Stages share a run id via the
``AGRISENTINEL_RUN_ID`` env var; when unset, processing stages operate on the
most recent run.
"""

from __future__ import annotations

import argparse
import sys

from agrisentinel.logging import get_logger

log = get_logger(__name__)


def _init_db(_args) -> int:
    from agrisentinel.db import ensure_extensions, run_sql_file

    ensure_extensions()
    run_sql_file("scripts/init_db.sql")
    log.info("Database initialised.")
    return 0


def _serve(args) -> int:
    import uvicorn

    uvicorn.run("api.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def _delegate(module: str):
    def _run(_args) -> int:
        mod = __import__(module, fromlist=["main"])
        return int(mod.main() or 0)

    return _run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agrisentinel", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Create extensions + schema (idempotent)").set_defaults(
        func=_init_db
    )

    # Ingestion
    sub.add_parser("ingest-stac", help="Fetch bi-temporal Sentinel-2 to MinIO").set_defaults(
        func=_delegate("ingestion.stac_fetch")
    )
    sub.add_parser("ingest-labels", help="Fetch Disfactory labels to PostGIS").set_defaults(
        func=_delegate("ingestion.labels_fetch")
    )
    sub.add_parser("load-parcels", help="Load farmland parcels to PostGIS").set_defaults(
        func=_delegate("ingestion.parcels_load")
    )
    sub.add_parser("fetch-laws", help="Chunk + embed statutes into pgvector").set_defaults(
        func=_delegate("ingestion.laws_fetch")
    )

    # Processing
    sub.add_parser("detect", help="Run change detection over the AOI").set_defaults(
        func=_delegate("processing.change_detect")
    )
    sub.add_parser("tile-detect", help="PySpark tiled change detection").set_defaults(
        func=_delegate("processing.spark_tiles")
    )
    sub.add_parser("join", help="Spatial-join detections × farmland parcels").set_defaults(
        func=_delegate("processing.zoning_join")
    )
    sub.add_parser("evaluate", help="Precision/recall vs Disfactory labels").set_defaults(
        func=_delegate("processing.evaluate")
    )

    # Agent
    sub.add_parser("dossiers", help="Generate enforcement dossiers (Claude RAG)").set_defaults(
        func=_delegate("agent.dossier_agent")
    )

    # Delivery
    serve = sub.add_parser("serve", help="Run the FastAPI app + dashboard")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=_serve)

    sub.add_parser("seed", help="Load bundled offline sample data").set_defaults(
        func=_delegate("agrisentinel.seed")
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
