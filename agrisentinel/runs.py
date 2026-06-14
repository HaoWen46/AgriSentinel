"""Run identifiers tie a detection batch to its downstream join/eval/dossiers.

Stages share a run id via the ``AGRISENTINEL_RUN_ID`` env var; when unset,
processing stages default to the most recent run found in the database.
"""

from __future__ import annotations

import datetime as _dt
import os

from agrisentinel.db import get_conn


def new_run_id() -> str:
    env = os.environ.get("AGRISENTINEL_RUN_ID")
    if env:
        return env
    return "run-" + _dt.datetime.now(_dt.UTC).strftime("%Y%m%d-%H%M%S")


def resolve_run_id() -> str | None:
    """The run to operate on: env override, else the latest in the DB."""
    env = os.environ.get("AGRISENTINEL_RUN_ID")
    if env:
        return env
    with get_conn() as conn:
        row = conn.execute(
            "SELECT run_id FROM detections ORDER BY created_at DESC LIMIT 1;"
        ).fetchone()
    return row[0] if row else None
