"""Project logging. Use ``get_logger(__name__)`` everywhere; never bare ``print``
inside library code (scripts may print their final human-facing summary)."""

from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root = logging.getLogger("agrisentinel")
    root.handlers[:] = [handler]
    root.setLevel(getattr(logging, level, logging.INFO))
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under the ``agrisentinel`` root."""
    _configure()
    # Normalise so loggers always live under the configured root.
    short = name.split(".")[-1] if name == "__main__" else name
    return logging.getLogger(f"agrisentinel.{short}")
