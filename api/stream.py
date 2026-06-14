"""Phase 6 — Redpanda/Kafka event wiring (velocity / stream paradigm).

A single topic carries pipeline events, each tagged with a ``type``:

* ``detection.completed`` — emitted after a detection run is persisted.
* ``dossiers.ready``      — emitted after the worker finishes join→eval→dossiers.

``emit_event`` is best-effort: if the broker is down it logs and returns, so the
batch pipeline never fails because of streaming. The **worker** turns a new
detection run into dossiers automatically (no manual rerun); the API tails the
same topic over SSE to push live updates to the dashboard.

Run the worker: ``uv run python -m api.stream``.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from collections.abc import Iterator

from agrisentinel.config import get_settings
from agrisentinel.logging import get_logger

log = get_logger(__name__)


def _bootstrap() -> list[str]:
    return [s.strip() for s in get_settings().kafka_bootstrap_servers.split(",") if s.strip()]


def _producer():
    from kafka import KafkaProducer

    return KafkaProducer(
        bootstrap_servers=_bootstrap(),
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        retries=2,
        acks=1,
        max_block_ms=5000,  # fail fast if the broker is unreachable (best-effort emit)
    )


def emit_event(event_type: str, payload: dict) -> bool:
    """Publish an event. Best-effort: returns False (and logs) if the broker is down."""
    settings = get_settings()
    event = {"type": event_type, "ts": _dt.datetime.now(_dt.UTC).isoformat(), **payload}
    try:
        prod = _producer()
        prod.send(settings.kafka_topic_detections, event)
        prod.flush(timeout=8)
        prod.close(timeout=5)
        log.info("Emitted event '%s' (%s).", event_type, payload.get("run_id"))
        return True
    except Exception as exc:
        log.warning("Could not emit event '%s' (broker down?): %s", event_type, exc)
        return False


def consume_events(group_id: str, from_beginning: bool = False) -> Iterator[dict]:
    """Yield decoded events from the topic (used by the API SSE endpoint)."""
    from kafka import KafkaConsumer

    settings = get_settings()
    consumer = KafkaConsumer(
        settings.kafka_topic_detections,
        bootstrap_servers=_bootstrap(),
        group_id=group_id,
        auto_offset_reset="earliest" if from_beginning else "latest",
        enable_auto_commit=True,
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        # default consumer_timeout_ms is infinite → block waiting for events
        # (setting 0 would StopIteration immediately and exit the worker loop).
    )
    try:
        for msg in consumer:
            yield msg.value
    finally:
        consumer.close()


def _run_pipeline_for(run_id: str) -> None:
    """join → evaluate → dossiers for a freshly-detected run."""
    os.environ["AGRISENTINEL_RUN_ID"] = run_id
    from agent.dossier_agent import main as dossiers_main
    from processing.evaluate import main as evaluate_main
    from processing.zoning_join import main as join_main

    join_main()
    evaluate_main()
    dossiers_main()


def worker() -> int:
    """Consume detection.completed events and drive the rest of the pipeline."""
    log.info("Stream worker started; waiting for detection.completed events.")
    for event in consume_events(group_id="agrisentinel-worker", from_beginning=True):
        if event.get("type") != "detection.completed":
            continue
        run_id = event.get("run_id")
        if not run_id:
            continue
        log.info("Worker: processing run '%s' → join/evaluate/dossiers.", run_id)
        try:
            _run_pipeline_for(run_id)
            emit_event("dossiers.ready", {"run_id": run_id})
        except Exception as exc:
            log.error("Worker failed for run '%s': %s", run_id, exc)
    return 0


def main() -> int:
    return worker()


if __name__ == "__main__":
    raise SystemExit(main())
