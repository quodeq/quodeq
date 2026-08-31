"""Run-dimension cache configuration and fetcher factory for the dashboard.

Split out of ``dashboard``: the caching concern (env-tuned sizes, the
process-wide LRU, its invalidation hook) is independent of run resolution and
payload assembly, and ``services.scoring`` reaches into the fetcher factory
directly. ``dashboard`` re-exports everything here, so the historical import
path still resolves.
"""
from __future__ import annotations

import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from quodeq.core.types import DimensionResult
from quodeq.services._cache import make_lru_dimension_fetcher


@dataclass
class DashboardCacheConfig:
    """Optional cache overrides for build_dashboard (mirrors AccumulatedCacheConfig)."""
    cache: OrderedDict[tuple, list[DimensionResult]] | None = None
    lock: threading.Lock | None = None
    max_size: int | None = None


_DEFAULT_RUN_DIM_CACHE_MAX = 256


def _run_dim_cache_max(override: int | None = None, env: dict[str, str] | None = None) -> int:
    """Return the run-dimension cache size limit. *override* bypasses env for testing."""
    if override is not None:
        return override
    try:
        return int((env or os.environ).get("QUODEQ_RUN_DIM_CACHE_MAX", str(_DEFAULT_RUN_DIM_CACHE_MAX)))
    except (ValueError, TypeError):
        return _DEFAULT_RUN_DIM_CACHE_MAX


class DimensionCache:
    """Thread-safe LRU-eligible store of run-dimension data (dict+lock+clear).

    Without a shared cache, every dashboard request used a fresh one (built
    fresh in ``_make_run_dimension_fetcher`` below), so re-fetching the same
    project's history (which ``collect_stale_dimensions`` /
    ``_collect_previous_scores`` / ``build_accumulated_trend`` all walk) cost
    ~750ms per request even on warm calls. The shared cache eliminates the
    cross-request I/O without compromising the per-request consistency
    guarantees (the cache is keyed by
    ``(reports_root, project, run_id, suppression_version)`` so a
    dismiss/delete produces a new key and never serves a pre-suppression
    score, and runs are immutable once finalized).

    Instantiable so tests get isolated caches; production shares the
    module-default instance below.
    """

    def __init__(self) -> None:
        self.data: OrderedDict[tuple, list[DimensionResult]] = OrderedDict()
        self.lock = threading.Lock()

    def clear(self) -> None:
        with self.lock:
            self.data.clear()

    def keys(self) -> list[tuple]:
        """Return a snapshot list of the cache's current keys, under lock."""
        with self.lock:
            return list(self.data.keys())


_shared_dimension_cache = DimensionCache()


def create_dimension_cache() -> tuple[OrderedDict[tuple, list[DimensionResult]], threading.Lock]:
    """Create the default run-dimension LRU cache and its lock.

    Override this factory to plug in a shared backend (e.g. a Redis-backed
    OrderedDict wrapper) for multi-worker deployments.  The returned
    ordered-dict must support ``move_to_end``, ``popitem(last=False)``,
    and standard ``__getitem__``/``__setitem__``/``__contains__``.
    """
    return OrderedDict(), threading.Lock()


def clear_shared_dimension_cache(cache: DimensionCache | None = None) -> None:
    """Drop all cached run-dimension data (e.g. after a formula change).

    Clears *cache*, defaulting to the module-wide instance production
    shares (the dashboard and the grade-formula-change hook).
    """
    (cache or _shared_dimension_cache).clear()


def _make_run_dimension_fetcher(
    reports_root: Path,
    project: str,
    cache: OrderedDict[tuple, list[DimensionResult]] | None = None,
    lock: threading.Lock | None = None,
    max_size: int | None = None,
    version: str = "",
) -> Callable[[str], list[DimensionResult]]:
    """Return a cached fetcher for run dimension data (LRU, bounded).

    Defaults to the module-level shared cache so reads of the same run's
    dimensions across requests reuse work. *version* scopes the cache key to the
    project's suppression state so a dismiss/delete invalidates it. Tests pass
    explicit cache/lock to isolate state.
    """
    return make_lru_dimension_fetcher(
        reports_root,
        project,
        cache if cache is not None else _shared_dimension_cache.data,
        lock if lock is not None else _shared_dimension_cache.lock,
        max_size if max_size is not None else _run_dim_cache_max(),
        version=version,
    )


__all__ = [
    "DashboardCacheConfig",
    "DimensionCache",
    "clear_shared_dimension_cache",
    "create_dimension_cache",
]
