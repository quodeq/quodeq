"""Dashboard and accumulated-view logic, split from action_provider_fs."""
from __future__ import annotations

import os
import threading
from collections import OrderedDict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from quodeq.core.types import DimensionResult, DimensionSummary, to_camel_dict

from quodeq.services.ports import (
    RunInfo,
    calculate_trend,
    list_runs,
    read_run_data,
    summarize_dimensions,
)
from quodeq.services._cache import make_lru_dimension_fetcher
from quodeq.services._dashboard_stale import collect_stale_dimensions
from quodeq.services._dashboard_trend import build_accumulated_trend
from quodeq.services.dim_resolution import is_eligible_for_default_view


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
_DEFAULT_MAX_HISTORY_RUNS = 100


def _max_history_runs(env: dict[str, str] | None = None) -> int:
    """Return the history-scan ceiling, honouring QUODEQ_MAX_HISTORY_RUNS."""
    raw = (env or os.environ).get("QUODEQ_MAX_HISTORY_RUNS")
    if not raw:
        return _DEFAULT_MAX_HISTORY_RUNS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_HISTORY_RUNS
    return value if value > 0 else _DEFAULT_MAX_HISTORY_RUNS


_DEFAULT_RUN_DIM_CACHE_MAX = 256


def _run_dim_cache_max(override: int | None = None, env: dict[str, str] | None = None) -> int:
    """Return the run-dimension cache size limit. *override* bypasses env for testing."""
    if override is not None:
        return override
    try:
        return int((env or os.environ).get("QUODEQ_RUN_DIM_CACHE_MAX", str(_DEFAULT_RUN_DIM_CACHE_MAX)))
    except (ValueError, TypeError):
        return _DEFAULT_RUN_DIM_CACHE_MAX


# Module-level shared cache for run-dimension data. Without this, every
# dashboard request used a fresh cache (created in _make_run_dimension_fetcher
# below), so re-fetching the same project's history (which collect_stale_dimensions
# / _collect_previous_scores / build_accumulated_trend all walk) cost ~750ms
# per request even on warm calls. The shared cache eliminates the cross-request
# I/O without compromising the per-request consistency guarantees (the cache
# is keyed by (reports_root, project, run_id) and runs are immutable once
# finalized).
#
# Tests that need isolation can pass an explicit DashboardCacheConfig.
_SHARED_RUN_DIM_CACHE, _SHARED_RUN_DIM_LOCK = OrderedDict(), threading.Lock()


def create_dimension_cache() -> tuple[OrderedDict[tuple, list[DimensionResult]], threading.Lock]:
    """Create the default run-dimension LRU cache and its lock.

    Override this factory to plug in a shared backend (e.g. a Redis-backed
    OrderedDict wrapper) for multi-worker deployments.  The returned
    ordered-dict must support ``move_to_end``, ``popitem(last=False)``,
    and standard ``__getitem__``/``__setitem__``/``__contains__``.
    """
    return OrderedDict(), threading.Lock()


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


def _make_run_dimension_fetcher(
    reports_root: Path,
    project: str,
    cache: OrderedDict[tuple, list[DimensionResult]] | None = None,
    lock: threading.Lock | None = None,
    max_size: int | None = None,
) -> Callable[[str], list[DimensionResult]]:
    """Return a cached fetcher for run dimension data (LRU, bounded).

    Defaults to the module-level shared cache so reads of the same run's
    dimensions across requests reuse work. Tests pass explicit cache/lock to
    isolate state.
    """
    return make_lru_dimension_fetcher(
        reports_root,
        project,
        cache if cache is not None else _SHARED_RUN_DIM_CACHE,
        lock if lock is not None else _SHARED_RUN_DIM_LOCK,
        max_size if max_size is not None else _run_dim_cache_max(),
    )


@dataclass
class _DashboardPayload:
    """Pre-computed parts for the dashboard response."""
    selected_summary: DimensionSummary
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
            {"runId": item.run_id, "dateISO": item.date_iso, "dateLabel": item.date_label, "status": item.status}
            for item in runs
        ],
        "selectedRun": {
            "runId": selected_run.run_id,
            "dateISO": selected_run.date_iso,
            "dateLabel": selected_run.date_label,
        },
        "summary": {
            **to_camel_dict(payload.selected_summary),
            "dateISO": selected_run.date_iso,
            "dateLabel": selected_run.date_label,
        },
        "trend": payload.trend,
        "dimensions": [to_camel_dict(d) for d in payload.dimensions_with_trend],
        "previousByDimension": {k: to_camel_dict(v) for k, v in payload.previous_by_dimension.items()},
        "stalePreviousByDimension": {k: to_camel_dict(v) for k, v in payload.stale_previous_by_dimension.items()},
        "staleDimensions": [to_camel_dict(d) for d in payload.stale_dimensions],
    }


def _resolve_selected_run(runs: list[RunInfo], run: str) -> tuple[RunInfo, int]:
    """Return the selected RunInfo and its index in *runs*, raising FileNotFoundError if absent.

    For ``run == _LATEST_RUN``, prefer the most recent run that's eligible
    to drive the default view (``complete`` or ``in_progress``). The
    eligibility predicate is the shared
    ``dim_resolution.is_eligible_for_default_view`` rule, used by both this
    call site and ``accumulated._compute_result``. Keeping them on the
    same predicate is what prevents the "headline says one thing, cards
    say another" inconsistency users hit when the two filters drift.

    If every run is cancelled (fresh project / repeated crashes), fall
    back to ``runs[0]`` rather than refusing to render. Users can still
    navigate to a specific partial run via the score-history chart.

    Note: run IDs are opaque UUIDs (no sensitive data), safe to include in
    error messages.
    """
    if run == _LATEST_RUN:
        selected_run = next(
            (r for r in runs if is_eligible_for_default_view(r.status)),
            runs[0],
        )
    else:
        selected_run = next((item for item in runs if item.run_id == run), None)
    if not selected_run:
        raise FileNotFoundError("Run not found")
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
    summary: DimensionSummary


def _compute_dashboard_payload(
    reports_root: Path, project: str, runs: list[RunInfo],
    ctx: _SelectedRunContext, cc: DashboardCacheConfig,
) -> _DashboardPayload:
    """Compute history-dependent parts of the dashboard response."""
    selected_dim_names = {d.dimension for d in ctx.dimensions}
    # Exclude cancelled/failed runs — they produce misleading points on the
    # history chart. They remain visible in availableRuns for the UI.
    scoreable_runs = [r for r in runs if r.status not in ("cancelled", "failed")]
    # Re-find the selected run's index inside scoreable_runs. ctx.index is
    # the index in the full unfiltered run list, which can exceed
    # len(history_runs) when cancelled/failed runs sit above the selected
    # run. Passing the wrong index to collect_stale_dimensions /
    # _collect_previous_scores caused IndexError on history_runs[newer_idx].
    selected_in_scoreable = next(
        (i for i, r in enumerate(scoreable_runs) if r.run_id == ctx.run.run_id),
        None,
    )
    max_history = _max_history_runs()
    if selected_in_scoreable is None:
        # Selected run was cancelled/failed (so it's not in scoreable_runs).
        # Treat the entire scoreable history as "older" runs relative to it.
        history_runs = scoreable_runs[:max_history]
        history_index = len(history_runs)
    else:
        history_runs = scoreable_runs[:max(max_history, selected_in_scoreable + 1)]
        history_index = selected_in_scoreable
    get_run_dimensions = _make_run_dimension_fetcher(
        reports_root, project, cache=cc.cache, lock=cc.lock, max_size=cc.max_size,
    )
    previous_by_dimension = _collect_previous_scores(
        history_runs, history_index, selected_dim_names, get_run_dimensions,
    )
    stale_dimensions, stale_previous_by_dimension = collect_stale_dimensions(
        history_runs, history_index, selected_dim_names, get_run_dimensions,
    )
    return _DashboardPayload(
        selected_summary=ctx.summary,
        trend=build_accumulated_trend(history_runs, get_run_dimensions),
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
        return {
            "project": project,
            "selectedRun": None,
            "dimensions": [],
            "summary": {},
            "trend": [],
        }

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
