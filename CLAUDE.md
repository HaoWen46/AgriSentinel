# CLAUDE.md — AgriSentinel build rules

Condensed operating rules for any agent (or human) working in this repo. The
full spec is `AgriSentinel_PROJECT_PLAN.md`; the assignment is
`BDA_Final_Project.pdf`.

## What this is
A thin, **working, end-to-end** pipeline that detects new structures on Changhua
farmland from Sentinel-2 imagery, joins them against parcel/zoning data in
PostGIS, and uses a Claude agent (RAG over Taiwanese statutes) to draft a
per-parcel **enforcement dossier**. The sold artifact is the dossier, not the
data. Optimize for *demonstrably working over one pilot township*, not
completeness.

## Hard rules
1. **Never hardcode machine state.** No absolute paths, hosts, or secrets in
   committed code. Everything comes from `.env` / environment / `config/*.yaml`.
   `DATA_DIR` defaults to a *relative* `./data`. Secrets live only in `.env`
   (gitignored).
2. **Idempotent & safe.** DDL uses `CREATE ... IF NOT EXISTS`; writes upsert;
   reruns must not corrupt state. Nothing destructive runs without an explicit
   flag.
3. **Use `uv` for all Python.** `uv sync`, `uv run python -m ...`. Never call a
   bare `pip`/`python`.
4. **Graceful degradation, never silent failure.** Heavy/optional capabilities
   (deep-learning detector, Spark, transformer embeddings) have light fallbacks
   (spectral detector, single-process tiling, TF-IDF+SVD). Fallbacks are logged
   loudly, never hidden. When `ALLOW_OFFLINE_FALLBACK=1`, ingestion may use
   bundled sample data if an upstream source is unreachable — and says so.
5. **No fabricated facts in dossiers.** Every factual claim must trace to a
   retrieved detection fact or statute chunk. Never label a parcel "illegal"
   without the zoning join confirming agricultural land.
6. **Cite, respect licences.** Sentinel-2 (open), Disfactory (CC BY 4.0),
   全國法規資料庫 (MOJ open data), NLSC (respect ToS). Attribute in the report.

## Architecture layers (build/extend in this order)
`ingestion/` → `processing/` → `agent/` → `api/` + `dashboard/`. Shared utils in
`agrisentinel/` (config, db, storage, geo, logging). One-command run via
`docker compose up`; orchestration shortcuts in the `Makefile`.

## Conventions
- Modules are runnable: `uv run python -m ingestion.stac_fetch`.
- Config access: `from agrisentinel.config import get_settings, get_aoi`.
- DB access: `from agrisentinel.db import connect` (psycopg3, PostGIS+pgvector).
- Object store: `from agrisentinel.storage import get_s3, ensure_bucket`.
- Log via `agrisentinel.logging.get_logger(__name__)`; no bare `print` in libs.
- Geometry math in `working_crs` (EPSG:3826, metres); store geoms as EPSG:4326.

## Phase gates (do not advance until acceptance passes)
0 infra up · 1 imagery+parcels+labels land · 2 change polygons persisted ·
3 ranked flagged parcels + precision/recall vs Disfactory · 4 ≥5 grounded
dossiers · 5 dashboard clickable · 6 new-imagery → event → dossier without rerun.

The Phase-3 precision/recall number is the technical-credibility anchor — never
skip it.
