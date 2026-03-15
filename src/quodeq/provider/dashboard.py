"""Dashboard and accumulated-view logic, split from action_provider_fs."""
from __future__ import annotations

import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from quodeq.adapters.fs.report_parser import (
    RunInfo,
    calculate_trend,
    list_runs,
    most_frequent_grade,
    read_run_data,
    summarize_dimensions,
)
from quodeq.provider._cache import make_lru_dimension_fetcher
from quodeq.provider._dashboard_stale import collect_stale_dimensions

# Re-export for backward compatibility (tests import this name)
_collect_stale_dimensions = collect_stale_dimensions
from quodeq.provider.accumulated import numeric_average


@dataclass
class DashboardCacheConfig:
    """Optional cache overrides for build_dashboard (mirrors AccumulatedCacheConfig)."""
    cache: OrderedDict[tuple, list[dict[str, Any]]] | None = None
    lock: threading.Lock | None = None
    max_size: int | None = None


_SKIP_GRADES = {"NA", "N/A", "INSUFFICIENT"}

# Maximum number of historical runs scanned for trend, previous scores, and
# stale dimensions. The full run list is still returned in availableRuns (metadata
# only, no disk reads) so users can navigate to older runs directly.
_LATEST_RUN = "latest"
_MAX_HISTORY_RUNS = 100

# NOTE: Process-local cache; not shared across workers. Replace with Redis/memcached for multi-worker deployments.
# Module-level LRU cache shared across requests; evicts least-recently-used
# entries once the limit is reached, capping memory while providing cross-
# request caching for hot-path dimension reads (P-TIM-6).
_RUN_DIM_CACHE: OrderedDict[tuple, list[dict[str, Any]]] = OrderedDict()
_RUN_DIM_LOCK = threading.Lock()


_DEFAULT_RUN_DIM_CACHE_MAX = 256


def _run_dim_cache_max(override: int | None = None) -> int:
    """Return the run-dimension cache size limit. *override* bypasses env for testing."""
    if override is not None:
        return override
    return int(os.environ.get("QUODEQ_RUN_DIM_CACHE_MAX", str(_DEFAULT_RUN_DIM_CACHE_MAX)))


def _collect_previous_scores(
    runs: list[RunInfo], selected_index: int, selected_dim_names: set[str],
    get_run_dimensions: Callable[[str], list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """Find the most recent previous score for each dimension in the selected run."""
    previous_by_dimension: dict[str, dict[str, Any]] = {}
    for older_idx in range(selected_index + 1, len(runs)):
        run_dimensions = get_run_dimensions(runs[older_idx].run_id)
        for dim in run_dimensions:
            dim_name = dim.get("dimension")
            if not dim_name or dim_name not in selected_dim_names:
                continue
            grade = dim.get("overallGrade")
            if not grade or str(grade).upper() in _SKIP_GRADES:
                continue
            if dim_name not in previous_by_dimension:
                previous_by_dimension[dim_name] = {**dim, "runId": runs[older_idx].run_id}
    return previous_by_dimension


def _enrich_dimensions_with_trend(
    selected_dimensions: list[dict[str, Any]], previous_by_dimension: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attach trend and previous-run data to each selected dimension."""
    result = []
    for dim in selected_dimensions:
        previous = previous_by_dimension.get(dim.get("dimension"))
        trend = calculate_trend(dim.get("overallScore"), previous.get("overallScore") if previous else None)
        result.append(
            {
                **dim,
                "trend": trend,
                "previousRunId": previous.get("runId") if previous else None,
                "previousScore": previous.get("overallScore") if previous else None,
            }
        )
    return result


def _build_accumulated_trend(
    runs: list[RunInfo],
    get_run_dimensions: Callable[[str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Build trend using accumulated scores across all runs (oldest to newest)."""
    trend: list[dict[str, Any]] = []
    acc_by_dim: dict[str, dict[str, Any]] = {}
    for item in reversed(runs):  # oldest -> newest
        run_dims = get_run_dimensions(item.run_id)
        for dim in run_dims:
            dim_name = dim.get("dimension")
            if dim_name:
                acc_by_dim[dim_name] = dim
        if not run_dims:
            continue
        acc_dims = list(acc_by_dim.values())
        acc_grades = [d.get("overallGrade") for d in acc_dims if d.get("overallGrade")]
        trend.append(
            {
                "runId": item.run_id,
                "dateISO": item.date_iso,
                "dateLabel": item.date_label,
                "dimensionsCount": len(acc_by_dim),
                "overallGrade": most_frequent_grade(acc_grades) if acc_grades else None,
                "numericAverage": numeric_average(acc_dims),
            }
        )
    trend.reverse()
    return trend


def _make_run_dimension_fetcher(
    reports_root: Path,
    project: str,
    cache: OrderedDict[tuple, list[dict[str, Any]]] | None = None,
    lock: threading.Lock | None = None,
    max_size: int | None = None,
) -> Callable[[str], list[dict[str, Any]]]:
    """Return a cached fetcher for run dimension data (LRU, bounded)."""
    return make_lru_dimension_fetcher(
        reports_root,
        project,
        cache if cache is not None else _RUN_DIM_CACHE,
        lock if lock is not None else _RUN_DIM_LOCK,
        max_size if max_size is not None else _run_dim_cache_max(),
    )


def _build_dashboard_result(
    *,
    project: str,
    runs: list[RunInfo],
    selected_run: RunInfo,
    selected_summary: dict[str, Any],
    trend: list[dict[str, Any]],
    dimensions_with_trend: list[dict[str, Any]],
    previous_by_dimension: dict[str, dict[str, Any]],
    stale_previous_by_dimension: dict[str, dict[str, Any]],
    stale_dimensions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the final dashboard response dict from pre-computed parts."""
    return {
        "project": project,
        "availableRuns": [
            {"runId": item.run_id, "dateISO": item.date_iso, "dateLabel": item.date_label}
            for item in runs
        ],
        "selectedRun": {
            "runId": selected_run.run_id,
            "dateISO": selected_run.date_iso,
            "dateLabel": selected_run.date_label,
        },
        "summary": {**selected_summary, "dateISO": selected_run.date_iso, "dateLabel": selected_run.date_label},
        "trend": trend,
        "dimensions": dimensions_with_trend,
        "previousByDimension": previous_by_dimension,
        "stalePreviousByDimension": stale_previous_by_dimension,
        "staleDimensions": stale_dimensions,
    }


def _resolve_selected_run(runs: list[RunInfo], run: str) -> tuple[RunInfo, int]:
    """Return the selected RunInfo and its index in *runs*, raising FileNotFoundError if absent."""
    selected_run = runs[0] if run == _LATEST_RUN else next((item for item in runs if item.run_id == run), None)
    if not selected_run:
        raise FileNotFoundError(f"Run not found: {run}")
    selected_index = next((idx for idx, item in enumerate(runs) if item.run_id == selected_run.run_id), None)
    if selected_index is None:
        raise RuntimeError(f"Run {selected_run.run_id!r} disappeared from the run list unexpectedly.")
    return selected_run, selected_index


def _resolve_dashboard_cache(
    cache_config: DashboardCacheConfig | None,
    cache: OrderedDict[tuple, list[dict[str, Any]]] | None,
    lock: threading.Lock | None,
    max_cache_size: int | None,
) -> DashboardCacheConfig:
    """Merge deprecated individual cache params into a DashboardCacheConfig."""
    if cache_config is not None:
        return cache_config
    if cache is not None or lock is not None or max_cache_size is not None:
        return DashboardCacheConfig(cache=cache, lock=lock, max_size=max_cache_size)
    return DashboardCacheConfig()


def build_dashboard(
    reports_dir: str,
    project: str,
    run: str,
    *,
    cache_config: DashboardCacheConfig | None = None,
    cache: OrderedDict[tuple, list[dict[str, Any]]] | None = None,
    lock: threading.Lock | None = None,
    max_cache_size: int | None = None,
) -> dict[str, Any]:
    """Build a full dashboard response for *project* at *run*.

    Pass *cache_config* to override the module-level LRU cache.
    """
    _cc = _resolve_dashboard_cache(cache_config, cache, lock, max_cache_size)
    reports_root = Path(reports_dir)
    runs = list_runs(reports_root, project)
    if not runs:
        raise FileNotFoundError(f"No runs found for project: {project}")

    selected_run, selected_index = _resolve_selected_run(runs, run)
    selected_dimensions = read_run_data(reports_root, project, selected_run.run_id)
    selected_summary = summarize_dimensions(selected_dimensions)
    selected_dim_names = {d.get("dimension") for d in selected_dimensions}

    history_runs = runs[:max(_MAX_HISTORY_RUNS, selected_index + 1)]
    get_run_dimensions = _make_run_dimension_fetcher(
        reports_root, project, cache=_cc.cache, lock=_cc.lock, max_size=_cc.max_size,
    )
    previous_by_dimension = _collect_previous_scores(history_runs, selected_index, selected_dim_names, get_run_dimensions)
    stale_dimensions, stale_previous_by_dimension = (
        collect_stale_dimensions(history_runs, selected_index, selected_dim_names, get_run_dimensions)
    )
    dimensions_with_trend = _enrich_dimensions_with_trend(selected_dimensions, previous_by_dimension)
    trend = _build_accumulated_trend(history_runs, get_run_dimensions)

    return _build_dashboard_result(
        project=project, runs=runs, selected_run=selected_run,
        selected_summary=selected_summary, trend=trend,
        dimensions_with_trend=dimensions_with_trend,
        previous_by_dimension=previous_by_dimension,
        stale_previous_by_dimension=stale_previous_by_dimension,
        stale_dimensions=stale_dimensions,
    )
