"""Dashboard and accumulated-view logic, split from action_provider_fs."""
from __future__ import annotations

import os
import threading
from collections import OrderedDict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from quodeq.core.types import DimensionResult, to_camel_dict

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
    cache: OrderedDict[tuple, list[DimensionResult]] | None = None
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
_RUN_DIM_CACHE: OrderedDict[tuple, list[DimensionResult]] = OrderedDict()
_RUN_DIM_LOCK = threading.Lock()


_DEFAULT_RUN_DIM_CACHE_MAX = 256


def _run_dim_cache_max(override: int | None = None) -> int:
    """Return the run-dimension cache size limit. *override* bypasses env for testing."""
    if override is not None:
        return override
    return int(os.environ.get("QUODEQ_RUN_DIM_CACHE_MAX", str(_DEFAULT_RUN_DIM_CACHE_MAX)))


def _collect_previous_scores(
    runs: list[RunInfo], selected_index: int, selected_dim_names: set[str],
    get_run_dimensions: Callable[[str], list[DimensionResult]],
) -> dict[str, DimensionResult]:
    """Find the most recent previous score for each dimension in the selected run."""
    previous_by_dimension: dict[str, DimensionResult] = {}
    for older_idx in range(selected_index + 1, len(runs)):
        run_dimensions = get_run_dimensions(runs[older_idx].run_id)
        for dim in run_dimensions:
            dim_name = dim.dimension
            if not dim_name or dim_name not in selected_dim_names:
                continue
            grade = dim.overall_grade
            if not grade or str(grade).upper() in _SKIP_GRADES:
                continue
            if dim_name not in previous_by_dimension:
                previous_by_dimension[dim_name] = replace(dim, run_id=runs[older_idx].run_id)
    return previous_by_dimension


def _enrich_dimensions_with_trend(
    selected_dimensions: list[DimensionResult], previous_by_dimension: dict[str, DimensionResult]
) -> list[DimensionResult]:
    """Attach trend and previous-run data to each selected dimension."""
    result: list[DimensionResult] = []
    for dim in selected_dimensions:
        previous = previous_by_dimension.get(dim.dimension or "")
        trend = calculate_trend(dim.overall_score, previous.overall_score if previous else None)
        result.append(
            replace(
                dim,
                trend=trend,
                previous_run_id=previous.run_id if previous else None,
                previous_score=previous.overall_score if previous else None,
            )
        )
    return result


def _build_accumulated_trend(
    runs: list[RunInfo],
    get_run_dimensions: Callable[[str], list[DimensionResult]],
) -> list[dict[str, Any]]:
    """Build trend using accumulated scores across all runs (oldest to newest)."""
    trend: list[dict[str, Any]] = []
    acc_by_dim: dict[str, DimensionResult] = {}
    for item in reversed(runs):  # oldest -> newest
        run_dims = get_run_dimensions(item.run_id)
        for dim in run_dims:
            if dim.dimension:
                acc_by_dim[dim.dimension] = dim
        if not run_dims:
            continue
        acc_dims = list(acc_by_dim.values())
        acc_grades = [d.overall_grade for d in acc_dims if d.overall_grade]
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
    cache: OrderedDict[tuple, list[DimensionResult]] | None = None,
    lock: threading.Lock | None = None,
    max_size: int | None = None,
) -> Callable[[str], list[DimensionResult]]:
    """Return a cached fetcher for run dimension data (LRU, bounded)."""
    return make_lru_dimension_fetcher(
        reports_root,
        project,
        cache if cache is not None else _RUN_DIM_CACHE,
        lock if lock is not None else _RUN_DIM_LOCK,
        max_size if max_size is not None else _run_dim_cache_max(),
    )


@dataclass
class _DashboardPayload:
    """Pre-computed parts for the dashboard response."""
    selected_summary: dict[str, Any]
    trend: list[dict[str, Any]]
    dimensions_with_trend: list[DimensionResult]
    previous_by_dimension: dict[str, DimensionResult]
    stale_previous_by_dimension: dict[str, DimensionResult]
    stale_dimensions: list[DimensionResult]


def _build_dashboard_result(
    project: str,
    runs: list[RunInfo],
    selected_run: RunInfo,
    payload: _DashboardPayload,
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
        "summary": {**payload.selected_summary, "dateISO": selected_run.date_iso, "dateLabel": selected_run.date_label},
        "trend": payload.trend,
        "dimensions": [to_camel_dict(d) for d in payload.dimensions_with_trend],
        "previousByDimension": {k: to_camel_dict(v) for k, v in payload.previous_by_dimension.items()},
        "stalePreviousByDimension": {k: to_camel_dict(v) for k, v in payload.stale_previous_by_dimension.items()},
        "staleDimensions": [to_camel_dict(d) for d in payload.stale_dimensions],
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


@dataclass(frozen=True)
class _SelectedRunContext:
    """Pre-resolved data for the selected run in a dashboard request."""
    run: RunInfo
    index: int
    dimensions: list[DimensionResult]
    summary: dict[str, Any]


def _compute_dashboard_payload(
    reports_root: Path, project: str, runs: list[RunInfo],
    ctx: _SelectedRunContext, cc: DashboardCacheConfig,
) -> _DashboardPayload:
    """Compute history-dependent parts of the dashboard response."""
    selected_dim_names = {d.dimension for d in ctx.dimensions}
    history_runs = runs[:max(_MAX_HISTORY_RUNS, ctx.index + 1)]
    get_run_dimensions = _make_run_dimension_fetcher(
        reports_root, project, cache=cc.cache, lock=cc.lock, max_size=cc.max_size,
    )
    previous_by_dimension = _collect_previous_scores(
        history_runs, ctx.index, selected_dim_names, get_run_dimensions,
    )
    stale_dimensions, stale_previous_by_dimension = collect_stale_dimensions(
        history_runs, ctx.index, selected_dim_names, get_run_dimensions,
    )
    return _DashboardPayload(
        selected_summary=ctx.summary,
        trend=_build_accumulated_trend(history_runs, get_run_dimensions),
        dimensions_with_trend=_enrich_dimensions_with_trend(ctx.dimensions, previous_by_dimension),
        previous_by_dimension=previous_by_dimension,
        stale_previous_by_dimension=stale_previous_by_dimension,
        stale_dimensions=stale_dimensions,
    )


def build_dashboard(
    reports_dir: str,
    project: str,
    run: str,
    *,
    cache_config: DashboardCacheConfig | None = None,
) -> dict[str, Any]:
    """Build a full dashboard response for *project* at *run*.

    Pass *cache_config* to override the module-level LRU cache.
    """
    cc = cache_config or DashboardCacheConfig()
    reports_root = Path(reports_dir)
    runs = list_runs(reports_root, project)
    if not runs:
        raise FileNotFoundError(f"No runs found for project: {project}")

    selected_run, selected_index = _resolve_selected_run(runs, run)
    selected_dims = read_run_data(reports_root, project, selected_run.run_id)
    ctx = _SelectedRunContext(
        run=selected_run,
        index=selected_index,
        dimensions=selected_dims,
        summary=summarize_dimensions(selected_dims),
    )
    payload = _compute_dashboard_payload(reports_root, project, runs, ctx, cc)
    return _build_dashboard_result(project, runs, selected_run, payload)
