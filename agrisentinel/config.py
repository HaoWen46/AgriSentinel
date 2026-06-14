"""Central configuration.

Two sources, kept strictly separate:

* **Environment / .env** → :func:`get_settings` (secrets, hosts, service URLs).
* **config/aoi_*.yaml**  → :func:`get_aoi` (the pilot AOI: bbox, dates, thresholds).

Nothing here encodes a machine-specific absolute path. ``repo_root`` is derived
from this file's location at runtime, and ``data_dir`` defaults to
``<repo_root>/data`` (overridable with ``DATA_DIR``).
"""

from __future__ import annotations

import functools
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def repo_root() -> Path:
    """Repository root, derived from this file's location (never hardcoded)."""
    return Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Environment-driven settings. All have safe local-dev defaults so the
    package imports (and tests run) without a populated ``.env``."""

    model_config = SettingsConfigDict(
        env_file=str(repo_root() / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Anthropic
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"

    # PostGIS (+pgvector)
    database_url: str = "postgresql://agrisentinel:agrisentinel@localhost:5432/agrisentinel"

    # MinIO / S3
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "agrisentinel"
    s3_secret_key: str = "agrisentinel"
    s3_bucket: str = "agrisentinel"
    s3_region: str = "us-east-1"

    # Redpanda / Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_detections: str = "agrisentinel.detections"

    # Pipeline
    aoi_config: str = "config/aoi_changhua.yaml"
    data_dir: str | None = None
    change_detector: str = "spectral"  # spectral | torchgeo
    embedder: str = "tfidf-svd"  # tfidf-svd | sentence-transformers
    embed_dim: int = 384
    pc_subscription_key: str | None = None
    allow_offline_fallback: bool = True
    log_level: str = "INFO"

    @property
    def data_path(self) -> Path:
        base = Path(self.data_dir) if self.data_dir else (repo_root() / "data")
        return base.resolve()


# ── Typed AOI model ──────────────────────────────────────────────────────────


class DateWindow(BaseModel):
    start: str
    end: str


class StacCfg(BaseModel):
    collection: str = "sentinel-2-l2a"
    bands: list[str]
    max_cloud_cover: float = 25
    t0: DateWindow
    t1: DateWindow


class TilingCfg(BaseModel):
    tile_size_m: float = 1280
    overlap_m: float = 0


class DetectionCfg(BaseModel):
    ndbi_delta_min: float = 0.06
    ndvi_drop_min: float = 0.12
    min_area_m2: float = 400
    morph_open_iter: int = 1
    max_candidates: int = 500
    match_radius_m: float = 80  # eval: a detection matches a label within this distance


class SyntheticParcels(BaseModel):
    grid_m: float = 120
    farmland_fraction: float = 0.7
    seed: int = 20260615


class ParcelsCfg(BaseModel):
    provider: str = "synthetic"  # synthetic | geojson | landuse
    path: str | None = None
    synthetic: SyntheticParcels = Field(default_factory=SyntheticParcels)


class LawRef(BaseModel):
    pcode: str
    title: str


class LawsCfg(BaseModel):
    pcodes: list[LawRef]
    chunk_chars: int = 600
    chunk_overlap: int = 80
    top_k: int = 6


class Center(BaseModel):
    lon: float
    lat: float


class AOI(BaseModel):
    name: str
    display_name: str
    county: str
    township: str
    bbox: list[float]  # [min_lon, min_lat, max_lon, max_lat]
    center: Center
    disfactory_range_km: float = 7
    working_crs: str = "EPSG:3826"
    stac: StacCfg
    tiling: TilingCfg = Field(default_factory=TilingCfg)
    detection: DetectionCfg = Field(default_factory=DetectionCfg)
    parcels: ParcelsCfg = Field(default_factory=ParcelsCfg)
    laws: LawsCfg

    @property
    def bbox_tuple(self) -> tuple[float, float, float, float]:
        return tuple(self.bbox)  # type: ignore[return-value]


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@functools.lru_cache(maxsize=8)
def _load_aoi(path: str) -> AOI:
    p = Path(path)
    if not p.is_absolute():
        p = repo_root() / p
    with p.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return AOI.model_validate(raw)


def get_aoi(path: str | None = None) -> AOI:
    """Load and validate the AOI config (defaults to ``settings.aoi_config``)."""
    return _load_aoi(path or get_settings().aoi_config)


def ensure_dir(path: Path) -> Path:
    """Create a directory (and parents) on demand; return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path
