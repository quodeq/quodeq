"""Dashboard and accumulated-view logic.

This module owns the *selected run*: resolving which run the request means,
rescoring its dimensions against project-wide suppressions, and driving the
three collaborators that do the rest.

- ``_dashboard_cache``    — run-dimension LRU config, shared cache, fetchers
- ``_dashboard_history``  — previous scores, stale dimensions, trend series
- ``_dashboard_response`` — camelCase serialization of the response

Their symbols are re-exported below so existing import paths keep resolving.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from quodeq.core.run.state import RunState
from quodeq.core.scoring.params import ScoringParams
from quodeq.core.scoring.report_grades import summarize_dimensions
from quodeq.core.types import DimensionResult
from quodeq.core.types.dashboard_view import DashboardView

from quodeq.services.scoring_view import is_eligible_for_default_view
from quodeq.services.wiring import (
    RunInfo,
    list_runs,
    read_run_data,
    row_dimension,
)
from quodeq.services.run_metadata import read_run_metadata
from quodeq.services.score_cache import run_rows
from quodeq.services.trend_fetcher import make_rescoring_fetcher

from quodeq.services._dashboard_cache import (  # noqa: F401
    DashboardCacheConfig,
    DEFAULT_RUN_DIM_CACHE_MAX,
    make_run_dimension_fetcher,
    run_dim_cache_max,
    clear_shared_dimension_cache,
    create_dimension_cache,
)
from quodeq.services._dashboard_history import (  # noqa: F401
    DashboardPayload,
    DEFAULT_MAX_HISTORY_RUNS,
    SKIP_GRADES,
    RunHistory,
    SelectedRunContext,
    collect_previous_scores,
    compute_dashboard_payload,
    enrich_dimensions_with_trend,
    max_history_runs,
    open_run_history,
    read_run_exit_reason,
)
from quodeq.services._dashboard_response import (  # noqa: F401
    DimensionAnnotations,
    attach_exit_reason_to_dim,
    build_dashboard_result,
    slim_history_dim,
)
from quodeq.services.run_constants import LATEST_RUN


def _make_status_aware_fetcher(
    reports_root: Path,
    project: str,
    runs: list[RunInfo],
    config: DashboardCacheConfig | None = None,
) -> Callable[[str], list[DimensionResult]]:
    """Return a fetcher that reads in-progress runs fresh, never from cache.

    The base LRU fetcher (``make_lru_dimension_fetcher``) already self-heals:
    on-disk count validation plus a status.json in-progress bypass. This
    wrapper adds the richer status from *runs* (``list_runs`` folds in a
    PID-liveness check that status.json alone can't see), so a run whose
    process is still alive reads fresh even before its state flips.
    """
    cached = make_run_dimension_fetcher(reports_root, project, config)
    status_by_id = {r.run_id: r.status for r in runs}

    def fetch(run_id: str) -> list[DimensionResult]:
        if status_by_id.get(run_id) is RunState.RUNNING:
            return read_run_data(reports_root, project, run_id)
        return cached(run_id)

    return fetch


# Fallback order for the "latest" default run when none is done. Each
# tier is tried newest-first; a failed run is only headlined when nothing
# else remains (handled after this list). Done mirrors the Overview's
# is_eligible_for_default_view; cancelled matches its cancelled fallback.
_LATEST_FALLBACK_ORDER = (
    is_eligible_for_default_view,               # done
    lambda status: status is RunState.CANCELLED,
    lambda status: status is RunState.RUNNING,
)


def _resolve_selected_run(runs: list[RunInfo], run: str) -> tuple[RunInfo, int]:
    """Return the selected RunInfo and its index in *runs*, raising FileNotFoundError if absent.

    For ``run == LATEST_RUN``, prefer the most recent ``done`` run.
    Running and cancelled runs are skipped: the overview waits for a
    run to terminate cleanly before promoting it to the default
    landing-page view. The eligibility predicate is the shared
    ``scoring_view.is_eligible_for_default_view`` rule, used by both
    this call site and ``accumulated._compute_result``. Keeping them on
    the same predicate is what prevents the "headline says one thing,
    cards say another" inconsistency users hit when the two filters
    drift.

    If no run is done (fresh project, only run still running,
    every attempt cancelled), fall back by trust order — cancelled, then
    running — and only headline a ``failed`` run when there is nothing
    else. A failed run must not headline the dashboard while a cancelled
    run with real kept-findings data exists, or the headline would show
    untrustworthy data the Overview cards (which never fall back to
    ``failed``) refuse to show. Users can still navigate to any specific
    run via the score-history chart or history table.

    Note: run IDs are opaque UUIDs (no sensitive data), safe to include in
    error messages.
    """
    if run == LATEST_RUN:
        selected_run = None
        for accept in _LATEST_FALLBACK_ORDER:
            selected_run = next((r for r in runs if accept(r.status)), None)
            if selected_run:
                break
        if selected_run is None:
            selected_run = runs[0]  # only failed runs remain; show the newest
    else:
        selected_run = next((item for item in runs if item.run_id == run), None)
    if not selected_run:
        raise FileNotFoundError("Run not found")
    selected_index = next((idx for idx, item in enumerate(runs) if item.run_id == selected_run.run_id), None)
    if selected_index is None:
        raise RuntimeError(f"Run {selected_run.run_id!r} disappeared from the run list unexpectedly.")
    return selected_run, selected_index


def _resolve_selected_dims(
    reports_root: Path, project: str, selected_run: RunInfo, params: ScoringParams,
) -> list[DimensionResult]:
    """Read the selected run's raw dims and rescore them with the project-wide
    ``rescore_dimension`` (the SQL grade overlay only knows dismissals projected
    into THIS run, so the accumulated view and this one would otherwise
    disagree). Each dimension carries what the dismissed and deleted filters
    hid (``dismissed_count`` / ``suppressed_count``), measured against the
    same dimensions the response ships, so shown + suppressed == what the
    scan found.
    """
    rescoring = make_rescoring_fetcher(
        reports_root, project, params,
        base_fetcher=lambda run_id: read_run_data(reports_root, project, run_id),
    )
    return rescoring(selected_run.run_id)


def _selected_dims_from_rows(history: RunHistory, selected_run: RunInfo) -> list[DimensionResult]:
    """The selected run's dimensions as the Overview shows them: its score-cache rows.

    The same rows the history walk serves (score, grade, counts, principles,
    hidden counts), with the findings never read: a hit is one bulk read the
    fetcher already made, a miss computes the run once and persists it. A run
    the cache cannot hold (in progress, or the cache disabled) is read fresh
    and slimmed here.
    """
    return [row_dimension(d) for d in run_rows(history.get_run_dimensions)(selected_run.run_id)]


def _resolve_params(params: ScoringParams | None) -> ScoringParams:
    """Return *params*, or the saved grade-formula params when None."""
    if params is not None:
        return params
    from quodeq.services import grade_formula  # noqa: PLC0415
    return grade_formula.load_params()


def _selected_dims(
    reports_root: Path, project: str, history: RunHistory, selected_run: RunInfo,
    params: ScoringParams, view: DashboardView,
) -> list[DimensionResult]:
    """The selected run's dimensions: the full view reads and rescores its
    findings, the overview serves it from its rows."""
    if view is DashboardView.OVERVIEW:
        return _selected_dims_from_rows(history, selected_run)
    return _resolve_selected_dims(reports_root, project, selected_run, params)


def build_dashboard(
    reports_dir: str,
    project: str,
    run: str,
    *,
    cache_config: DashboardCacheConfig | None = None,
    params: ScoringParams | None = None,
    view: DashboardView = DashboardView.FULL,
) -> dict[str, Any]:
    """Build a full dashboard response for *project* at *run*.

    Pass *cache_config* to override the module-level LRU cache.

    When *params* is None, the saved grade-formula params are loaded once
    here and threaded through the run-level summary, SQL grade override, and
    trend so the dashboard rollup honours the user's custom formula.
    """
    params = _resolve_params(params)
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
    history = open_run_history(reports_root, project, runs, selected_run.run_id, cc, params)
    dims = _selected_dims(reports_root, project, history, selected_run, params, view)
    ctx = SelectedRunContext(
        run=selected_run,
        index=selected_index,
        dimensions=dims,
        summary=summarize_dimensions(dims, params),
        runs=runs,
    )
    annotations = DimensionAnnotations(
        exit_reason=read_run_exit_reason(reports_root, project, selected_run.run_id), view=view,
    )
    payload = compute_dashboard_payload(reports_root, project, ctx, history, params)
    metadata = read_run_metadata(reports_root / project / ctx.run.run_id)
    return build_dashboard_result(project, runs, ctx.run, payload, annotations, run_metadata=metadata)


__all__ = [
    "DashboardCacheConfig",
    "build_dashboard",
    "clear_shared_dimension_cache",
    "create_dimension_cache",
]
