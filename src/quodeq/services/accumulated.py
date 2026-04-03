"""Accumulated (cross-run) view logic for the filesystem action provider."""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quodeq.services.ports import RunInfo, list_runs
from quodeq.core.types import DimensionResult
from quodeq.shared.utils import _env_int
from quodeq.services._cache import make_lru_dimension_fetcher
from quodeq.services.dismissed import filter_dismissed_from_dimensions

# Re-export helpers so existing external imports keep working.
from quodeq.services._accumulated_data import _read_all_run_data  # noqa: F401
from quodeq.services._accumulated_helpers import (  # noqa: F401
    _AccumulatedResult,
    _aggregate_severity_counts,
    _build_accumulated_response,
    _compute_accumulated_scores,
    _compute_accumulated_trends,
    numeric_average,
)

_DEFAULT_ACC_CACHE_MAX = 256


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


def _compute_result(
    reports_root: Path, project: str, all_run_infos: list[RunInfo],
    cache_config: AccumulatedCacheConfig | None,
) -> _AccumulatedResult:
    """Load run data and compute trends, severity, and scores."""
    runs = [r.run_id for r in all_run_infos]
    _cache, _lock, _max = _resolve_cache(cache_config)
    get_run_data = make_lru_dimension_fetcher(reports_root, project, _cache, _lock, _max)
    latest_by_dim, prev_occurrence, prev_run_latest = _read_all_run_data(
        reports_root, project, all_run_infos, runs, get_run_data,
    )
    all_dims = filter_dismissed_from_dimensions(list(latest_by_dim.values()), reports_root / project)
    dims_with_trend = _compute_accumulated_trends(all_dims, prev_occurrence)
    severity = _aggregate_severity_counts(all_dims)
    avg, prev_avg = _compute_accumulated_scores(all_dims, prev_run_latest)
    return _AccumulatedResult(all_dims, dims_with_trend, severity, avg, prev_avg)


def compute_accumulated(
    reports_dir: str, project: str, as_of: str | None,
    *, cache_config: AccumulatedCacheConfig | None = None,
) -> dict[str, Any] | None:
    """Compute the accumulated (cross-run) view for *project*."""
    reports_root = Path(reports_dir)
    if not (reports_root / project).exists():
        return None
    all_run_infos = list_runs(reports_root, project)
    if as_of:
        idx = next((i for i, r in enumerate(all_run_infos) if r.run_id == as_of), None)
        all_run_infos = all_run_infos[idx:] if idx is not None else []
    if not all_run_infos:
        return None
    return _build_accumulated_response(project, _compute_result(reports_root, project, all_run_infos, cache_config))
