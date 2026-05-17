"""Compare legacy rescore output to SQL-backed output, log divergences.

Used during the one-release soak after PR 2. Frontend is unaffected -- the
endpoint returns the SQL output; the legacy path runs only for comparison.
Disabled by default; enable with QUODEQ_GRADE_PARITY_LOG=1.

Note: legacy `_legacy_get_scores_raw` reads FS-level graded output files,
not events.jsonl. Test runs that seed only events (no FS grade files) will
show legacy=empty, which is expected and noisy. The logger flags any
non-empty divergence -- review the production logs over the soak period to
decide when to delete the legacy path.
"""
from __future__ import annotations

import logging
import os
from typing import Any

_logger = logging.getLogger(__name__)

_ENABLE_KEY = "QUODEQ_GRADE_PARITY_LOG"


def is_enabled() -> bool:
    """Return True when QUODEQ_GRADE_PARITY_LOG=1 is set."""
    return os.environ.get(_ENABLE_KEY) == "1"


def log_divergence_if_any(
    *,
    legacy: dict[str, Any],
    sql: dict[str, Any],
    run_id: str,
) -> None:
    """Compare per-dimension overallScore between two payloads. Log a warning per divergence."""
    legacy_dims = {d.get("dimension"): d.get("overallScore") for d in legacy.get("dimensions", [])}
    sql_dims = {d.get("dimension"): d.get("overallScore") for d in sql.get("dimensions", [])}

    all_dims = set(legacy_dims) | set(sql_dims)
    diffs = {
        name: (legacy_dims.get(name), sql_dims.get(name))
        for name in all_dims
        if legacy_dims.get(name) != sql_dims.get(name)
    }
    if not diffs:
        return

    for name, (legacy_score, sql_score) in diffs.items():
        _logger.warning(
            "Grade parity divergence in run %s, dimension %s: legacy=%s, sql=%s",
            run_id, name, legacy_score, sql_score,
        )
