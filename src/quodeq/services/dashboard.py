"""Dashboard and accumulated-view logic, split from action_provider_fs.

This module owns the *selected run*: resolving which run the request means,
rescoring its dimensions against project-wide suppressions, and driving the
three collaborators that do the rest.

- ``_dashboard_cache``    — run-dimension LRU config, shared cache, fetchers
- ``_dashboard_history``  — previous scores, stale dimensions, trend series
- ``_dashboard_response`` — camelCase serialization of the response

Their symbols are re-exported below so existing import paths keep resolving.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

from quodeq.core.scoring.params import ScoringParams
from quodeq.core.types import DimensionResult

from quodeq.data.fs.report_parser.grades import summarize_dimensions
from quodeq.data.fs.report_parser.runs import RunInfo, list_runs, read_run_data
from quodeq.services.deleted import deleted_keys
from quodeq.services.scoring_view import is_eligible_for_default_view
from quodeq.services.dismissed import dismissed_keys, filter_dismissed_from_dimensions
from quodeq.services.ports import load_suppression_rules
from quodeq.services.rescore import _rescore_dimension
from quodeq.shared.validation import validate_path_segment

from quodeq.services._dashboard_cache import (  # noqa: F401
    DashboardCacheConfig,
    _DEFAULT_RUN_DIM_CACHE_MAX,
    _make_run_dimension_fetcher,
    _run_dim_cache_max,
    _SHARED_RUN_DIM_CACHE,
    _SHARED_RUN_DIM_LOCK,
    clear_shared_dimension_cache,
    create_dimension_cache,
)
from quodeq.services._dashboard_history import (  # noqa: F401
    _DashboardPayload,
    _DEFAULT_MAX_HISTORY_RUNS,
    _SKIP_GRADES,
    _SelectedRunContext,
    _collect_previous_scores,
    _compute_dashboard_payload,
    _enrich_dimensions_with_trend,
    _max_history_runs,
    _read_run_exit_reason,
)
from quodeq.services._dashboard_response import (  # noqa: F401
    _attach_dismissed_count_to_dim,
    _attach_exit_reason_to_dim,
    _build_dashboard_result,
    _slim_history_dim,
)

_LATEST_RUN = "latest"


def _rescore_run_dimensions(
    dims: list[DimensionResult],
    reports_root: Path,
    project: str,
    run_id: str,
    params: ScoringParams,
) -> list[DimensionResult]:
    """Apply the project-wide dismiss/delete rescore to a run's dimensions.

    Identity when the project has no active dismissals/deletions. Otherwise each
    dimension passes through the same ``_rescore_dimension`` transform the
    accumulated view and the per-run explorer use, so every read path reports
    the identical dismiss-adjusted score/grade. *run_id* is the run the *dims*
    were read from: its directory is passed as the evidence basis so a touched
    dimension is re-scored from that run's own evidence, not the legacy formula.
    """
    validate_path_segment(project)
    project_dir = reports_root / project
    dismissed = dismissed_keys(project_dir)
    deleted = deleted_keys(project_dir)
    rules = load_suppression_rules(project_dir)
    # Rules count as suppression state; see scored_run_dimensions.
    if not dismissed and not deleted and not rules:
        return dims
    validate_path_segment(run_id)
    run_dir = project_dir / run_id
    return [
        _rescore_dimension(d, dismissed, deleted, params=params, run_dir=run_dir,
                           rules=rules)
        for d in dims
    ]


def _make_status_aware_fetcher(
    reports_root: Path,
    project: str,
    runs: list[RunInfo],
    cache: OrderedDict[tuple, list[DimensionResult]] | None = None,
    lock: threading.Lock | None = None,
    max_size: int | None = None,
    version: str = "",
) -> Callable[[str], list[DimensionResult]]:
    """Return a fetcher that reads in-progress runs fresh, never from cache.

    The base LRU fetcher (``make_lru_dimension_fetcher``) already self-heals:
    on-disk count validation plus a status.json in-progress bypass. This
    wrapper adds the richer status from *runs* (``list_runs`` folds in a
    PID-liveness check that status.json alone can't see), so a run whose
    process is still alive reads fresh even before its state flips.
    """
    cached = _make_run_dimension_fetcher(
        reports_root, project,
        cache=cache, lock=lock, max_size=max_size, version=version,
    )
    status_by_id = {r.run_id: r.status for r in runs}

    def fetch(run_id: str) -> list[DimensionResult]:
        if status_by_id.get(run_id) == "in_progress":
            return read_run_data(reports_root, project, run_id)
        return cached(run_id)

    return fetch


# Fallback order for the "latest" default run when none is complete. Each
# tier is tried newest-first; a failed run is only headlined when nothing
# else remains (handled after this list). Complete mirrors the Overview's
# is_eligible_for_default_view; cancelled matches its cancelled fallback.
_LATEST_FALLBACK_ORDER = (
    is_eligible_for_default_view,               # complete
    lambda status: status == "cancelled",
    lambda status: status == "in_progress",
)


def _resolve_selected_run(runs: list[RunInfo], run: str) -> tuple[RunInfo, int]:
    """Return the selected RunInfo and its index in *runs*, raising FileNotFoundError if absent.

    For ``run == _LATEST_RUN``, prefer the most recent ``complete`` run.
    in_progress and cancelled runs are skipped: the overview waits for a
    run to terminate cleanly before promoting it to the default
    landing-page view. The eligibility predicate is the shared
    ``scoring_view.is_eligible_for_default_view`` rule, used by both
    this call site and ``accumulated._compute_result``. Keeping them on
    the same predicate is what prevents the "headline says one thing,
    cards say another" inconsistency users hit when the two filters
    drift.

    If no run is complete (fresh project, only run still in progress,
    every attempt cancelled), fall back by trust order — cancelled, then
    in_progress — and only headline a ``failed`` run when there is nothing
    else. A failed run must not headline the dashboard while a cancelled
    run with real kept-findings data exists, or the headline would show
    untrustworthy data the Overview cards (which never fall back to
    ``failed``) refuse to show. Users can still navigate to any specific
    run via the score-history chart or history table.

    Note: run IDs are opaque UUIDs (no sensitive data), safe to include in
    error messages.
    """
    if run == _LATEST_RUN:
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


def build_dashboard(
    reports_dir: str,
    project: str,
    run: str,
    *,
    cache_config: DashboardCacheConfig | None = None,
    params: ScoringParams | None = None,
) -> dict[str, Any]:
    """Build a full dashboard response for *project* at *run*.

    Pass *cache_config* to override the module-level LRU cache.

    When *params* is None, the saved grade-formula params are loaded once
    here and threaded through the run-level summary, SQL grade override, and
    trend so the dashboard rollup honours the user's custom formula.
    """
    if params is None:
        from quodeq.services import grade_formula  # noqa: PLC0415
        params = grade_formula.load_params()
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
    # ``read_run_data`` overlays the run's SQL grade tables, but those grades
    # only reflect dismissals projected into THIS run and NOT project-wide
    # dismissals/deletions that accrued later -- so the raw selected-run score
    # can disagree with the accumulated overview. Rescore the selected run's
    # dimensions with the SAME project-wide ``_rescore_dimension`` transform the
    # accumulated view and the per-run explorer use, so every path reports the
    # identical dismiss-adjusted score/grade AND drops the dismissed + deleted
    # violations from the counts. ``read_run_data`` stays the dimension source
    # here (a stable seam other callers and tests inject through).
    project_dir = reports_root / project
    raw_dims = read_run_data(reports_root, project, selected_run.run_id)
    # ``dismissedCount`` reports how many of the scan's re-found violations were
    # hidden by the *dismissed* filter specifically (deletions are a separate,
    # permanent suppression), so measure it against the dismissed-only filter.
    pre_filter_counts = {d.dimension: len(d.violations) for d in raw_dims}
    dismissed_only = filter_dismissed_from_dimensions(raw_dims, project_dir)
    dismissed_counts = {
        (d.dimension or ""): pre_filter_counts.get(d.dimension, 0) - len(d.violations)
        for d in dismissed_only
    }
    selected_dims = _rescore_run_dimensions(
        raw_dims, reports_root, project, selected_run.run_id, params)
    # Measured against the SAME dimensions the response ships, so the number
    # the UI shows always reconciles: shown + suppressed == what the scan found.
    suppressed_counts = {
        (d.dimension or ""): pre_filter_counts.get(d.dimension, 0) - len(d.violations)
        for d in selected_dims
    }
    ctx = _SelectedRunContext(
        run=selected_run,
        index=selected_index,
        dimensions=selected_dims,
        summary=summarize_dimensions(selected_dims, params),
    )
    payload = _compute_dashboard_payload(reports_root, project, runs, ctx, cc, params)
    exit_reason = _read_run_exit_reason(reports_root, project, selected_run.run_id)
    return _build_dashboard_result(
        project, runs, selected_run, payload,
        exit_reason=exit_reason, dismissed_counts=dismissed_counts,
        suppressed_counts=suppressed_counts,
    )


__all__ = [
    "DashboardCacheConfig",
    "build_dashboard",
    "clear_shared_dimension_cache",
    "create_dimension_cache",
]
