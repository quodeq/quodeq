"""Dashboard and accumulated-view logic, split from action_provider_fs."""
from __future__ import annotations

import logging
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
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
from quodeq.services._trend_fetcher import make_trend_fetcher
from quodeq.services.scoring_view import is_eligible_for_default_view, select_trend_runs
from quodeq.services.dismissed import filter_dismissed_from_dimensions

_logger = logging.getLogger(__name__)


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
# is keyed by (reports_root, project, run_id, suppression_version) so a
# dismiss/delete produces a new key and never serves a pre-suppression score,
# and runs are immutable once finalized).
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


def clear_shared_dimension_cache() -> None:
    """Drop all cached run-dimension data (e.g. after a formula change)."""
    with _SHARED_RUN_DIM_LOCK:
        _SHARED_RUN_DIM_CACHE.clear()


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
        cache if cache is not None else _SHARED_RUN_DIM_CACHE,
        lock if lock is not None else _SHARED_RUN_DIM_LOCK,
        max_size if max_size is not None else _run_dim_cache_max(),
        version=version,
    )


def _rescore_run_dimensions(
    dims: list[DimensionResult],
    reports_root: Path,
    project: str,
    params: ScoringParams,
) -> list[DimensionResult]:
    """Apply the project-wide dismiss/delete rescore to a run's dimensions.

    Identity when the project has no active dismissals/deletions. Otherwise each
    dimension passes through the same ``_rescore_dimension`` transform the
    accumulated view and the per-run explorer use, so every read path reports
    the identical dismiss-adjusted score/grade.
    """
    from quodeq.services.deleted import deleted_keys  # noqa: PLC0415
    from quodeq.services.dismissed import dismissed_keys  # noqa: PLC0415
    from quodeq.services.rescore import _rescore_dimension  # noqa: PLC0415

    project_dir = reports_root / project
    dismissed = dismissed_keys(project_dir)
    deleted = deleted_keys(project_dir)
    if not dismissed and not deleted:
        return dims
    return [_rescore_dimension(d, dismissed, deleted, params=params) for d in dims]


def _count_eval_files(reports_root: Path, project: str, run_id: str) -> int:
    """Count ``evaluation/*.json`` files on disk for a run.

    Used to detect a stale cache: if the cached dim list has a different
    count from what's currently on disk, the cache is wrong and must be
    evicted. One ``listdir`` per cached lookup -- cheap.
    """
    eval_dir = reports_root / project / run_id / "evaluation"
    if not eval_dir.is_dir():
        return 0
    try:
        return sum(1 for p in eval_dir.iterdir() if p.suffix == ".json")
    except OSError:
        return 0


def _make_status_aware_fetcher(
    reports_root: Path,
    project: str,
    runs: list[RunInfo],
    cache: OrderedDict[tuple, list[DimensionResult]] | None = None,
    lock: threading.Lock | None = None,
    max_size: int | None = None,
    version: str = "",
) -> Callable[[str], list[DimensionResult]]:
    """Return a fetcher with two self-healing properties on top of the LRU cache.

    1. **In-progress bypass.** Runs with status=in_progress have a mutable
       on-disk evaluation/ set as dims finish. We read directly from disk
       and don't write to cache, so the next request also reads fresh.

    2. **On-disk count validation for terminal runs.** Even after a run
       completes, the cache may hold a stale partial dim set -- e.g. if
       it was populated by a request that fired between dims being scored
       (a window opened by the BrokenPipe-during-success-log regression
       PR #481 fixed). On lookup, we count evaluation/*.json files and
       compare against the cached length. Mismatch -> evict, re-read.

    Cost: one extra ``listdir`` per cached lookup. Cheap (eval/ is small).
    """
    resolved_cache = cache if cache is not None else _SHARED_RUN_DIM_CACHE
    resolved_lock = lock if lock is not None else _SHARED_RUN_DIM_LOCK
    cached = _make_run_dimension_fetcher(
        reports_root, project,
        cache=resolved_cache, lock=resolved_lock, max_size=max_size, version=version,
    )
    status_by_id = {r.run_id: r.status for r in runs}

    def fetch(run_id: str) -> list[DimensionResult]:
        if status_by_id.get(run_id) == "in_progress":
            return read_run_data(reports_root, project, run_id)
        # Validate any cached entry against the on-disk count. If they
        # disagree, the cache is stale -- evict so the cached() call below
        # re-reads from disk and re-caches with the correct value. We only
        # validate when an actual evaluation/ directory exists on disk:
        # without that anchor we'd evict every test stub that pre-seeds
        # the cache without creating disk state.
        key = (reports_root, project, run_id, version)
        if key in resolved_cache:
            eval_dir = reports_root / project / run_id / "evaluation"
            if eval_dir.is_dir():
                on_disk = _count_eval_files(reports_root, project, run_id)
                if len(resolved_cache[key]) != on_disk:
                    with resolved_lock:
                        resolved_cache.pop(key, None)
        return cached(run_id)

    return fetch


@dataclass
class _DashboardPayload:
    """Pre-computed parts for the dashboard response."""
    selected_summary: DimensionSummary
    trend: list[dict[str, Any]]
    dimensions_with_trend: list[DimensionResult]
    previous_by_dimension: dict[str, DimensionResult]
    stale_previous_by_dimension: dict[str, DimensionResult]
    stale_dimensions: list[DimensionResult]


def _read_run_exit_reason(reports_root: Path, project: str, run_id: str) -> str | None:
    """Return the run's ``status.json`` ``exit_reason``, or ``None`` if absent.

    Used by the dashboard to surface deadline-truncated runs to the UI:
    the "Partial" badge on each DimensionGaugeCard fires when the run
    didn't complete naturally (e.g. ``exit_reason="deadline"`` from a
    timeout, or ``"failure_streak"`` from repeated failures).
    """
    import json as _json  # noqa: PLC0415
    status_path = reports_root / project / run_id / "status.json"
    if not status_path.is_file():
        return None
    try:
        with status_path.open("r", encoding="utf-8") as fp:
            data = _json.load(fp)
    except (OSError, ValueError):
        return None
    reason = data.get("exit_reason")
    return reason if isinstance(reason, str) else None


def _attach_exit_reason_to_dim(
    dim_dict: dict[str, Any], run_exit_reason: str | None,
) -> dict[str, Any]:
    """Add ``exitReason`` to a serialized dimension dict.

    Preference order: per-dim exit_reason (if present on the dim) wins over
    the run-level value. Either way, the chosen reason is exposed to the UI
    as ``exitReason``. Falls back to no key when both are absent (legacy).
    """
    per_dim = dim_dict.get("exit_reason") or dim_dict.get("exitReason")
    chosen = per_dim or run_exit_reason
    if chosen is None:
        # Drop the snake_case key if present, to keep the response clean.
        if "exit_reason" in dim_dict:
            out = dict(dim_dict)
            out.pop("exit_reason", None)
            return out
        return dim_dict
    out = dict(dim_dict)
    out.pop("exit_reason", None)
    out["exitReason"] = chosen
    return out


def _attach_dismissed_count_to_dim(
    dim_dict: dict[str, Any], dismissed_counts: dict[str, int],
) -> dict[str, Any]:
    """Add ``dismissedCount`` to a serialized dimension dict when > 0.

    The count says how many of the scan's re-found violations were hidden by
    the project-level dismissed filter, so the UI can explain the gap between
    "what the scan found" and "what the view shows". Omitted when nothing was
    filtered, mirroring the exitReason convention.
    """
    count = dismissed_counts.get(dim_dict.get("dimension") or "", 0)
    if count <= 0:
        return dim_dict
    return {**dim_dict, "dismissedCount": count}


def _slim_history_dim(dim: DimensionResult) -> dict[str, Any]:
    """Serialize a history-context dimension without its finding bodies.

    The previousByDimension / stalePreviousByDimension / staleDimensions keys
    exist to carry scores, grades, and provenance (run id, dates) for trend
    context; the UI reads only the scalar fields inlined on each selected-run
    dimension (previousScore, trend, stale, fromRunId). No consumer reads the
    violations/compliance arrays from these keys, yet on large projects they
    dominated the payload: for a 201-run project, an old run's dashboard was
    19.9 MB of which these three keys carried 18.6 MB of finding bodies.
    Totals keep the counts; only the bodies are dropped.
    """
    return to_camel_dict(replace(dim, violations=[], compliance=[]))


def _build_dashboard_result(
    project: str,
    runs: list[RunInfo],
    selected_run: RunInfo,
    payload: _DashboardPayload,
    *,
    exit_reason: str | None = None,
    dismissed_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Assemble the final dashboard response dict from pre-computed parts."""
    dim_dicts = [
        _attach_dismissed_count_to_dim(
            _attach_exit_reason_to_dim(to_camel_dict(d), exit_reason),
            dismissed_counts or {},
        )
        for d in payload.dimensions_with_trend
    ]
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
            "exitReason": exit_reason,
        },
        "summary": {
            **to_camel_dict(payload.selected_summary),
            "dateISO": selected_run.date_iso,
            "dateLabel": selected_run.date_label,
        },
        "trend": payload.trend,
        "dimensions": dim_dicts,
        "previousByDimension": {k: _slim_history_dim(v) for k, v in payload.previous_by_dimension.items()},
        "stalePreviousByDimension": {k: _slim_history_dim(v) for k, v in payload.stale_previous_by_dimension.items()},
        "staleDimensions": [_slim_history_dim(d) for d in payload.stale_dimensions],
    }


def _resolve_selected_run(runs: list[RunInfo], run: str) -> tuple[RunInfo, int]:
    """Return the selected RunInfo and its index in *runs*, raising FileNotFoundError if absent.

    For ``run == _LATEST_RUN``, prefer the most recent ``complete`` run.
    in_progress and cancelled runs are skipped: the overview waits for a
    run to terminate cleanly before promoting it to the default
    landing-page view. The eligibility predicate is the shared
    ``dim_resolution.is_eligible_for_default_view`` rule, used by both
    this call site and ``accumulated._compute_result``. Keeping them on
    the same predicate is what prevents the "headline says one thing,
    cards say another" inconsistency users hit when the two filters
    drift.

    If no run is complete (fresh project, only run still in progress,
    every attempt cancelled), fall back to ``runs[0]`` rather than
    refusing to render. Users can still navigate to a specific partial
    run via the score-history chart or history table.

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
    selected_dims = _rescore_run_dimensions(raw_dims, reports_root, project, params)
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
    )
