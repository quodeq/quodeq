"""Read scored dimensions for a single run from disk, with an LRU cache."""
from __future__ import annotations

import os
import threading
from collections import OrderedDict
from pathlib import Path

from quodeq.core.types import DimensionResult
from quodeq.services._cache import make_lru_dimension_fetcher

_DEFAULT_CACHE_MAX = int(os.environ.get("QUODEQ_DEFAULT_CACHE_MAX", "256"))

# Module-level cache shared across callers in the same process. Quodeq's
# server is single-process, so this is intentional. Multi-process setups
# can inject their own ``cache``/``cache_lock`` to bypass shared state.
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
