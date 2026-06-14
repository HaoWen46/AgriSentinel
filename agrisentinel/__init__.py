"""AgriSentinel — shared utilities for the farmland-factory detection pipeline.

Sub-packages mirror the architecture layers (see ``AgriSentinel_PROJECT_PLAN.md`` §3):
``ingestion`` → ``processing`` → ``agent`` → ``api``. This package holds the
cross-cutting helpers (config, logging, db, storage, geo) they all depend on.
"""

__version__ = "0.1.0"
