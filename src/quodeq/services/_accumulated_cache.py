"""The process-lived walk cache and the per-call accumulated-view LRU cache.

Split (Task 14) out of ``accumulated.py``. The walk-cache globals
(``_WALK_CACHE``/``_WALK_CACHE_LOCK``) are process-wide shared mutable state:
``accumulated.py`` re-exports the OBJECTS themselves (not copies), so tests
reaching in directly via ``clear_accumulated_process_cache`` see the same
cache instance the computation path reads and writes.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field

from quodeq.core.types import DimensionResult
from quodeq.shared.utils import _env_int

_DEFAULT_ACC_CACHE_MAX = 256

# Entries in the walk cache are findings-free (kilobytes), not full run reads
# (megabytes), so this bound covers several projects' entire run history and
# still costs a few MB. Set QUODEQ_ACC_WALK_CACHE_MAX=0 to disable.
_DEFAULT_WALK_CACHE_MAX = 2048

# Process-lived so consecutive as-of selections on the Overview score-history
# chart reuse the walk. Their run sets overlap in all but a run or two; a
# per-call cache made every newly-selected day re-read the whole history.
_WALK_CACHE: OrderedDict[tuple, list[DimensionResult]] = OrderedDict()
_WALK_CACHE_LOCK = threading.Lock()


def clear_accumulated_process_cache() -> None:
    """Drop the process-lived walk cache. For tests and cache kill switches."""
    with _WALK_CACHE_LOCK:
        _WALK_CACHE.clear()


def _walk_cache_max(override: int | None = None, env: dict[str, str] | None = None) -> int:
    """Return the walk-cache size limit (entries)."""
    if override is not None:
        return override
    return _env_int("QUODEQ_ACC_WALK_CACHE_MAX", _DEFAULT_WALK_CACHE_MAX, env=env)


def create_accumulated_cache() -> tuple[OrderedDict[tuple, list[DimensionResult]], threading.Lock]:
    """Create the default accumulated-view LRU cache and its lock."""
    return OrderedDict(), threading.Lock()


def _acc_dim_cache_max(override: int | None = None, env: dict[str, str] | None = None) -> int:
    """Return the accumulated-view cache size limit."""
    if override is not None:
        return override
    return _env_int("QUODEQ_ACC_CACHE_MAX", _DEFAULT_ACC_CACHE_MAX, env=env)


@dataclass
class AccumulatedCacheConfig:
    """Optional cache parameters for compute_accumulated."""
    cache: OrderedDict[tuple, list[DimensionResult]] = field(default_factory=OrderedDict)
    cache_lock: threading.Lock = field(default_factory=threading.Lock)
    cache_max: int | None = None


def _resolve_cache(
    cache_config: AccumulatedCacheConfig | None,
) -> tuple[OrderedDict, threading.Lock, int]:
    """Resolve cache, lock, and max-size from *cache_config* or module defaults."""
    if cache_config is not None:
        return (
            cache_config.cache,
            cache_config.cache_lock,
            cache_config.cache_max if cache_config.cache_max is not None else _acc_dim_cache_max(),
        )
    cache, lock = create_accumulated_cache()
    return cache, lock, _acc_dim_cache_max()
