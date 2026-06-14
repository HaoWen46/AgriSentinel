"""Phase 3 — precision / recall of flagged farmland parcels vs Disfactory labels.

This metric is the technical-credibility anchor (plan §6): it tells the customer
how often the pipeline's flags coincide with known illegal factories.

* **Precision** = flagged detections within ``match_radius_m`` of a known label
  ÷ all flagged detections.
* **Recall** = known labels with ≥1 flagged detection within ``match_radius_m``
  ÷ all known labels.

Disfactory labels are crowd-reported and incomplete, so these are *indicative*,
not absolute — stated plainly in the report. Writes a metrics row + JSON.

Run: ``uv run python -m processing.evaluate``.
"""

from __future__ import annotations

import json

from agrisentinel.config import ensure_dir, get_aoi, get_settings
from agrisentinel.db import get_conn
from agrisentinel.logging import get_logger
from agrisentinel.runs import resolve_run_id

log = get_logger(__name__)


def compute_metrics(run_id: str, aoi_name: str, radius_m: float) -> dict:
    with get_conn() as conn, conn.cursor() as cur:
        n_detections = cur.execute(
            "SELECT count(*) FROM detections WHERE run_id=%s;", (run_id,)
        ).fetchone()[0]
        n_flagged_det = cur.execute(
            "SELECT count(DISTINCT detection_id) FROM flagged_parcels WHERE run_id=%s;", (run_id,)
        ).fetchone()[0]
        tp_det = cur.execute(
            """SELECT count(DISTINCT detection_id) FROM flagged_parcels
               WHERE run_id=%s AND distance_to_label_m IS NOT NULL
                 AND distance_to_label_m <= %s;""",
            (run_id, radius_m),
        ).fetchone()[0]
        n_labels = cur.execute(
            "SELECT count(*) FROM labels WHERE aoi=%s;", (aoi_name,)
        ).fetchone()[0]
        labels_matched = cur.execute(
            """SELECT count(*) FROM labels l WHERE l.aoi=%s AND EXISTS (
                 SELECT 1 FROM flagged_parcels f WHERE f.run_id=%s
                 AND ST_DWithin(ST_Transform(f.geom,3826), ST_Transform(l.geom,3826), %s));""",
            (aoi_name, run_id, radius_m),
        ).fetchone()[0]

    precision = (tp_det / n_flagged_det) if n_flagged_det else 0.0
    recall = (labels_matched / n_labels) if n_labels else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "run_id": run_id,
        "aoi": aoi_name,
        "match_radius_m": radius_m,
        "n_detections": int(n_detections),
        "n_flagged_detections": int(n_flagged_det),
        "n_true_positive_detections": int(tp_det),
        "n_labels": int(n_labels),
        "n_labels_matched": int(labels_matched),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "note": "Disfactory labels are crowd-reported and incomplete; treat as indicative.",
    }


def main() -> int:
    aoi = get_aoi()
    settings = get_settings()
    run_id = resolve_run_id()
    if not run_id:
        raise RuntimeError("No run found. Run `detect` and `join` first.")
    metrics = compute_metrics(run_id, aoi.name, aoi.detection.match_radius_m)

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO metrics (run_id, aoi, payload) VALUES (%s, %s, %s);",
            (run_id, aoi.name, json.dumps(metrics)),
        )
    out_dir = ensure_dir(settings.data_path / "metrics")
    (out_dir / f"{run_id}.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    log.info(
        "Run '%s': precision=%.2f recall=%.2f f1=%.2f (%d flagged / %d labels, radius %.0fm)",
        run_id, metrics["precision"], metrics["recall"], metrics["f1"],
        metrics["n_flagged_detections"], metrics["n_labels"], metrics["match_radius_m"],
    )
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
