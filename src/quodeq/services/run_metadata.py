"""Per-run facts the dashboard shows next to the numbers: commit, formula and cache statistics.

Coverage (files read, source count, percentage) already travels on each
dimension entry of the dashboard payload, so this reads only what the
reports do not cover: status.json, dim_estimates.json and the formula
version stamped on the run's SQL grade tables.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from quodeq.services.wiring import SQLiteStateStore, evaluation_db_stamp, read_status
from quodeq.shared.dim_estimates_io import read_dim_estimates
from quodeq.shared.stamp_memo import StampCache, memoized_by_stamp

_KEY_COMMIT_SHA = "commit_sha"
_KEY_GRADE_ALGO_VERSION = "grade_algo_version"
_ESTIMATE_MISSES = "count"
_ESTIMATE_CACHED = "cached"
_ESTIMATE_EXCLUDED = "excluded"

# The grade tables' stamp only moves when they are recomputed, so a warm
# dashboard read pays a stat of the run database, not a connection.
_GRADES_VERSION_CACHE = StampCache(max_entries=512, name="grades_algo_version")


def _read_grades_version(run_dir: Path) -> tuple[int | None]:
    # Boxed so an unstamped run (None) is memoized too.
    try:
        return (SQLiteStateStore(run_dir).get_grades_algo_version(),)
    except (sqlite3.Error, RuntimeError):
        return (None,)


def read_grades_algo_version(run_dir: Path) -> int | None:
    """Formula version the run's SQL grade tables were computed with.

    None when the run has no evaluation.db (a legacy run keeps the grade its
    report stored), its tables carry no stamp yet, or the database cannot be read.
    """
    stamp = evaluation_db_stamp(run_dir)
    if stamp is None:
        return None
    boxed = memoized_by_stamp(str(run_dir), stamp, lambda: _read_grades_version(run_dir),
                              cache=_GRADES_VERSION_CACHE)
    return boxed[0] if boxed is not None else None


def read_run_metadata(run_dir: Path) -> dict[str, Any]:
    """Commit SHA and grade formula version from status.json, the formula
    version the SQL grade tables carry, and per-dimension cache hits / misses /
    provider-excluded counts from dim_estimates.json. Missing inputs yield
    None / empty, never an error."""
    status = read_status(run_dir) or {}
    cache_stats = {
        dim: {
            "cached": estimate.get(_ESTIMATE_CACHED),
            "misses": estimate.get(_ESTIMATE_MISSES),
            "excluded": estimate.get(_ESTIMATE_EXCLUDED),
        }
        for dim, estimate in read_dim_estimates(run_dir).items()
    }
    return {
        "commitSha": status.get(_KEY_COMMIT_SHA),
        "gradeAlgoVersion": status.get(_KEY_GRADE_ALGO_VERSION),
        "gradesAlgoVersion": read_grades_algo_version(run_dir),
        "cacheStats": cache_stats,
    }
