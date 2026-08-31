"""History-dependent parts of the dashboard response.

Split out of ``dashboard``: everything here walks the project's *older* runs
(previous scores, stale dimensions, the trend series) to build context for the
selected run. ``dashboard`` owns the selected run itself and re-exports these
helpers, so the historical import path still resolves.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.types import DimensionResult, DimensionSummary

from quodeq.services._dashboard_cache import DashboardCacheConfig, _make_run_dimension_fetcher
from quodeq.services._dashboard_stale import collect_stale_dimensions
from quodeq.services._dashboard_trend import build_accumulated_trend
from quodeq.services._trend_fetcher import make_trend_fetcher
from quodeq.services._wiring import RunInfo, calculate_trend, read_run_status_json
from quodeq.services.scoring_view import select_trend_runs

_SKIP_GRADES = {"NA", "N/A", "INSUFFICIENT"}


def _read_run_exit_reason(reports_root: Path, project: str, run_id: str) -> str | None:
    """Return the run's ``status.json`` ``exit_reason``, or ``None`` if absent.

    Used by the dashboard to surface deadline-truncated runs to the UI:
    the "Partial" badge on each DimensionGaugeCard fires when the run
    didn't complete naturally (e.g. ``exit_reason="deadline"`` from a
    timeout, or ``"failure_streak"`` from repeated failures).
    """
    data = read_run_status_json(reports_root / project / run_id)
    reason = data.get("exit_reason")
    return reason if isinstance(reason, str) else None


# Maximum number of historical runs scanned for trend, previous scores, and
# stale dimensions. The full run list is still returned in availableRuns (metadata
# only, no disk reads) so users can navigate to older runs directly.
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


@dataclass
class _DashboardPayload:
    """Pre-computed parts for the dashboard response."""
    selected_summary: DimensionSummary
    trend: list[dict[str, Any]]
    dimensions_with_trend: list[DimensionResult]
    previous_by_dimension: dict[str, DimensionResult]
    stale_previous_by_dimension: dict[str, DimensionResult]
    stale_dimensions: list[DimensionResult]


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
    params: ScoringParams = DEFAULT_PARAMS,
) -> _DashboardPayload:
    """Compute history-dependent parts of the dashboard response."""
    selected_dim_names = {d.dimension for d in ctx.dimensions}
    # Shared trend rule (scoring_view.select_trend_runs): cancelled/failed
    # runs are excluded — misleading history points. They remain visible in
    # availableRuns for the UI.
    scoreable_runs = select_trend_runs(runs)
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
    # History fetcher: cache-backed, dismiss-adjusted, SCALAR-only -- the same
    # fetcher the /scores endpoint uses. The three consumers below
    # (_collect_previous_scores, collect_stale_dimensions, build_accumulated_trend)
    # read only per-run scalars (dimension + overallScore + overallGrade), not
    # the full violations. Reading + rescoring FULL data for every history run
    # (up to _max_history_runs()) was the ~2s cost this replaces.
    #
    # In-progress freshness is preserved: the fast path re-reads each request
    # (fresh per-call cache), and the heavy path's cacheable_run_ids guard makes
    # in-progress runs compute-through without persisting a partial set. Stale-
    # partial detection is preserved inside read_run_scalars, which falls back to
    # full read_run_data whenever the SQL scalar projection disagrees with the
    # on-disk evaluation/*.json count -- the same self-heal the old status-aware
    # fetcher did via _count_eval_files. The dismiss-adjustment (Bug B) stays;
    # it is now cached rather than recomputed on every request.
    cacheable_run_ids = {r.run_id for r in history_runs if r.status == "complete"}
    # Key the in-memory dimension cache by the project's suppression state so a
    # dismiss/delete (or a formula change) invalidates warmed entries and no
    # read path can serve a pre-dismiss score. ``score_cache_version`` already
    # hashes dismissed + deleted keys + params. This fetcher is SHARED across the
    # whole history window (previous-scores, stale-dimensions, and the trend all
    # iterate many runs through it), so we keep the global project-scoped version
    # here rather than a per-run scoped one -- per-run scoping only makes sense
    # when a single run is in play, which this path is not.
    from quodeq.services.score_cache import score_cache_version  # noqa: PLC0415
    dim_cache_version = score_cache_version(reports_root / project, params)
    get_run_dimensions = make_trend_fetcher(
        reports_root, project, params=params, cacheable_run_ids=cacheable_run_ids,
        max_history=max_history,
        base_fetcher_factory=lambda rr, proj: _make_run_dimension_fetcher(
            rr, proj, cache=cc.cache, lock=cc.lock, max_size=cc.max_size,
            version=dim_cache_version,
        ),
    )
    previous_by_dimension = _collect_previous_scores(
        history_runs, history_index, selected_dim_names, get_run_dimensions,
    )
    stale_dimensions, stale_previous_by_dimension = collect_stale_dimensions(
        history_runs, history_index, selected_dim_names, get_run_dimensions,
    )
    return _DashboardPayload(
        selected_summary=ctx.summary,
        trend=build_accumulated_trend(history_runs, get_run_dimensions, params=params),
        dimensions_with_trend=_enrich_dimensions_with_trend(ctx.dimensions, previous_by_dimension),
        previous_by_dimension=previous_by_dimension,
        stale_previous_by_dimension=stale_previous_by_dimension,
        stale_dimensions=stale_dimensions,
    )
