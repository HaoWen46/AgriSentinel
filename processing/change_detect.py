"""Phase 2 — bi-temporal change detection over the AOI.

Default detector is **spectral**: between the two dates it flags pixels where the
built-up index (NDBI) rises *and* the vegetation index (NDVI) falls — the
signature of new construction replacing farmland — then vectorises connected
regions into candidate polygons with per-polygon stats and a confidence score.

A ``torchgeo`` (Siamese-UNet / OSCD) path is a documented extension point; when
selected but not wired, it falls back to spectral with a loud warning. The
detector interface is intentionally swappable (see plan §4).

Run: ``uv run python -m processing.change_detect``.
"""

from __future__ import annotations

import numpy as np
from rasterio import features
from shapely.geometry import shape

from agrisentinel.config import AOI, get_aoi, get_settings
from agrisentinel.db import get_conn
from agrisentinel.geo import WGS84, area_m2, reproject_geom, wkt
from agrisentinel.logging import get_logger
from agrisentinel.raster import load_manifest, load_window
from agrisentinel.runs import new_run_id

log = get_logger(__name__)


def _index(num: np.ndarray, den_a: np.ndarray, den_b: np.ndarray) -> np.ndarray:
    denom = den_a + den_b
    out = np.zeros_like(denom, dtype="float32")
    np.divide(num, denom, out=out, where=denom != 0)
    return out


def ndvi(bands: dict[str, np.ndarray]) -> np.ndarray:
    return _index(bands["B08"] - bands["B04"], bands["B08"], bands["B04"])


def ndbi(bands: dict[str, np.ndarray]) -> np.ndarray:
    return _index(bands["B11"] - bands["B08"], bands["B11"], bands["B08"])


def _binary_open(mask: np.ndarray, iters: int) -> np.ndarray:
    """4-neighbour erosion then dilation (numpy-only) to drop speckle."""
    for _ in range(max(0, iters)):
        m = mask
        up, down = np.roll(m, -1, 0), np.roll(m, 1, 0)
        left, right = np.roll(m, -1, 1), np.roll(m, 1, 1)
        eroded = m & up & down & left & right
        u, d = np.roll(eroded, -1, 0), np.roll(eroded, 1, 0)
        ll, rr = np.roll(eroded, -1, 1), np.roll(eroded, 1, 1)
        mask = eroded | u | d | ll | rr
    return mask


def detect_spectral(aoi: AOI) -> list[dict]:
    cfg = aoi.detection
    t0_bands, transform, crs, _ = load_window(aoi.name, "t0")
    t1_bands, _, _, _ = load_window(aoi.name, "t1")

    delta_ndbi = ndbi(t1_bands) - ndbi(t0_bands)
    drop_ndvi = ndvi(t0_bands) - ndvi(t1_bands)
    mask = (delta_ndbi >= cfg.ndbi_delta_min) & (drop_ndvi >= cfg.ndvi_drop_min)
    mask = _binary_open(mask, cfg.morph_open_iter)
    log.info("Change mask: %d / %d pixels flagged.", int(mask.sum()), mask.size)

    detections: list[dict] = []
    for geom_raster, val in features.shapes(mask.astype("uint8"), mask=mask, transform=transform):
        if int(val) != 1:
            continue
        poly_r = shape(geom_raster)
        if not poly_r.is_valid:
            poly_r = poly_r.buffer(0)
        poly_wgs = reproject_geom(poly_r, str(crs), WGS84)
        a = area_m2(poly_wgs, aoi.working_crs)
        if a < cfg.min_area_m2:
            continue
        pix = features.geometry_mask([geom_raster], mask.shape, transform, invert=True)
        md = float(delta_ndbi[pix].mean()) if pix.any() else 0.0
        mv = float(drop_ndvi[pix].mean()) if pix.any() else 0.0
        conf = float(np.clip(0.5 * min(md / 0.30, 1.0) + 0.5 * min(mv / 0.50, 1.0), 0.05, 0.99))
        detections.append(
            {"geom": poly_wgs, "area_m2": a, "ndbi_delta": md, "ndvi_drop": mv, "confidence": conf}
        )

    detections.sort(key=lambda d: d["confidence"], reverse=True)
    if len(detections) > cfg.max_candidates:
        log.warning("Capping detections %d → %d (detection.max_candidates).",
                    len(detections), cfg.max_candidates)
        detections = detections[: cfg.max_candidates]
    log.info("Spectral detector produced %d candidate polygons.", len(detections))
    return detections


def detect(aoi: AOI, detector: str) -> list[dict]:
    if detector == "torchgeo":
        try:
            import torchgeo  # noqa: F401

            log.warning(
                "torchgeo is installed but the OSCD weights path is a documented "
                "extension, not wired in the MVP — using the spectral detector. "
                "# TODO(scale): plug a pretrained Siamese-UNet here."
            )
        except Exception:
            log.warning("CHANGE_DETECTOR=torchgeo but torchgeo not installed → spectral.")
    return detect_spectral(aoi)


def persist(aoi: AOI, run_id: str, detector: str, detections: list[dict]) -> None:
    m0, m1 = load_manifest(aoi.name, "t0"), load_manifest(aoi.name, "t1")
    t0d = (m0.get("datetime") or "")[:10]
    t1d = (m1.get("datetime") or "")[:10]
    with get_conn() as conn, conn.cursor() as cur:
        for d in detections:
            cur.execute(
                """
                INSERT INTO detections (run_id, aoi, detector, t0_date, t1_date,
                                        ndbi_delta, ndvi_drop, confidence, area_m2, geom)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                        ST_SetSRID(ST_GeomFromText(%s), 4326));
                """,
                (run_id, aoi.name, detector, t0d, t1d, d["ndbi_delta"], d["ndvi_drop"],
                 d["confidence"], d["area_m2"], wkt(d["geom"])),
            )


def main() -> int:
    aoi = get_aoi()
    settings = get_settings()
    run_id = new_run_id()
    log.info("Change detection run '%s' (detector=%s).", run_id, settings.change_detector)
    detections = detect(aoi, settings.change_detector)
    persist(aoi, run_id, settings.change_detector, detections)
    log.info("Run '%s': persisted %d detections.", run_id, len(detections))

    from api.stream import emit_event  # best-effort; no-op if broker down

    emit_event("detection.completed", {"run_id": run_id, "aoi": aoi.name,
                                       "n_detections": len(detections),
                                       "detector": settings.change_detector})
    print(run_id)  # so callers / Makefile can capture the run id
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
