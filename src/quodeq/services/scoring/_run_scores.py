"""Read scores from a single run -- the ONLY module that touches disk."""
from __future__ import annotations

import os
import threading
from collections import OrderedDict
from pathlib import Path

from quodeq.core.types import DimensionResult
from quodeq.services._cache import make_lru_dimension_fetcher
from quodeq.services.ports import RunInfo, list_runs, parse_numeric_score

_DEFAULT_CACHE_MAX = int(os.environ.get("QUODEQ_DEFAULT_CACHE_MAX", "256"))

# Module-level shared cache so all callers within the same process share it.
# This is intentional for single-process deployment (the quodeq server runs
# as a single process).  For multi-process setups, callers can inject their
# own cache and lock via the `cache` and `cache_lock` parameters of
# get_run_dimensions(), completely bypassing this process-local state.
_cache: OrderedDict[tuple, list[DimensionResult]] = OrderedDict()
_cache_lock = threading.Lock()


def get_run_dimensions(
    reports_root: Path, project: str, run_id: str,
    *, cache: OrderedDict | None = None,
    cache_lock: threading.Lock | None = None,
    cache_max: int = _DEFAULT_CACHE_MAX,
) -> list[DimensionResult]:
    """Return dimension data for a single run, using the shared LRU cache."""
    c = cache if cache is not None else _cache
    lk = cache_lock if cache_lock is not None else _cache_lock
    fetcher = make_lru_dimension_fetcher(reports_root, project, c, lk, cache_max)
    return fetcher(run_id)


def get_available_runs(reports_root: Path, project: str) -> list[RunInfo]:
    """Return all runs for a project, sorted newest-first."""
    return list_runs(reports_root, project)


def parse_score(score_str: str | None) -> float | None:
    """Parse a score string like '7.5/10' into a float."""
    if not score_str:
        return None
    return parse_numeric_score(score_str)
