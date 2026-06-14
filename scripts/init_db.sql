-- AgriSentinel schema. Idempotent: safe to run on every startup.
-- Geometries stored in EPSG:4326; measured in EPSG:3826 by the application.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Parcels: farmland / zoning layer with cadastral number (地號) ──────────────
CREATE TABLE IF NOT EXISTS parcels (
    parcel_id     TEXT PRIMARY KEY,
    aoi           TEXT NOT NULL,
    landcode      TEXT,                       -- 地號 (may be synthetic)
    sectname      TEXT,                       -- 段名
    sectcode      TEXT,
    landuse_code  TEXT,                       -- land-use classification
    is_farmland   BOOLEAN NOT NULL DEFAULT FALSE,
    source        TEXT NOT NULL,              -- synthetic | geojson | landuse
    geom          geometry(Polygon, 4326) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS parcels_geom_gix ON parcels USING GIST (geom);
CREATE INDEX IF NOT EXISTS parcels_farmland_ix ON parcels (is_farmland);

-- ── Labels: Disfactory known illegal factories (evaluation ground truth) ──────
CREATE TABLE IF NOT EXISTS labels (
    id             TEXT PRIMARY KEY,          -- Disfactory uuid
    aoi            TEXT NOT NULL,
    display_number INTEGER,
    name           TEXT,
    landcode       TEXT,                      -- 地號
    townname       TEXT,
    sectname       TEXT,
    sectcode       TEXT,
    source         TEXT,
    factory_type   TEXT,
    status         TEXT,
    reported_at    TIMESTAMPTZ,
    geom           geometry(Point, 4326) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS labels_geom_gix ON labels USING GIST (geom);

-- ── Detections: candidate change polygons from the bi-temporal CD job ─────────
CREATE TABLE IF NOT EXISTS detections (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL,
    aoi         TEXT NOT NULL,
    detector    TEXT NOT NULL,               -- spectral | torchgeo
    t0_date     TEXT,
    t1_date     TEXT,
    ndbi_delta  REAL,
    ndvi_drop   REAL,
    confidence  REAL,
    area_m2     REAL,
    geom        geometry(Polygon, 4326) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS detections_geom_gix ON detections USING GIST (geom);
CREATE INDEX IF NOT EXISTS detections_run_ix ON detections (run_id);

-- ── Flagged parcels: detections ∩ farmland parcels (the ranked output) ────────
CREATE TABLE IF NOT EXISTS flagged_parcels (
    id               BIGSERIAL PRIMARY KEY,
    run_id           TEXT NOT NULL,
    detection_id     BIGINT REFERENCES detections(id) ON DELETE CASCADE,
    parcel_id        TEXT REFERENCES parcels(parcel_id) ON DELETE SET NULL,
    aoi              TEXT NOT NULL,
    landcode         TEXT,
    sectname         TEXT,
    is_farmland      BOOLEAN,
    overlap_area_m2  REAL,
    confidence       REAL,
    rank             INTEGER,
    matched_label_id TEXT,                    -- nearest Disfactory label, if any
    distance_to_label_m REAL,
    geom             geometry(Polygon, 4326) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS flagged_geom_gix ON flagged_parcels USING GIST (geom);
CREATE INDEX IF NOT EXISTS flagged_run_ix ON flagged_parcels (run_id);

-- ── Regulation chunks for the dossier RAG (pgvector) ──────────────────────────
-- `embedding` is an unconstrained vector so EMBED_DIM / embedder choice can
-- change without a migration; cosine search is brute-force over a few hundred rows.
CREATE TABLE IF NOT EXISTS law_chunks (
    id          BIGSERIAL PRIMARY KEY,
    pcode       TEXT NOT NULL,
    law_title   TEXT NOT NULL,
    article_no  TEXT,
    chunk_index INTEGER NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pcode, chunk_index)
);

-- ── Dossiers: the sold artifact ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dossiers (
    id            BIGSERIAL PRIMARY KEY,
    flagged_id    BIGINT REFERENCES flagged_parcels(id) ON DELETE CASCADE,
    run_id        TEXT NOT NULL,
    parcel_id     TEXT,
    landcode      TEXT,
    model         TEXT,
    confidence    REAL,
    violated_law  TEXT,
    recommended_action TEXT,
    dossier_md    TEXT,
    dossier_json  JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (flagged_id)
);

-- ── Metrics: evaluation results (precision/recall vs Disfactory) ──────────────
CREATE TABLE IF NOT EXISTS metrics (
    id         BIGSERIAL PRIMARY KEY,
    run_id     TEXT NOT NULL,
    aoi        TEXT,
    payload    JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
