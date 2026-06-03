"""Dashboard and accumulated-view logic, split from action_provider_fs."""
from __future__ import annotations

import logging
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
        cache=resolved_cache, lock=resolved_lock, max_size=max_size,
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
        key = (reports_root, project, run_id)
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


def _build_dashboard_result(
    project: str,
    runs: list[RunInfo],
    selected_run: RunInfo,
    payload: _DashboardPayload,
    *,
    exit_reason: str | None = None,
) -> dict[str, Any]:
    """Assemble the final dashboard response dict from pre-computed parts."""
    dim_dicts = [
        _attach_exit_reason_to_dim(to_camel_dict(d), exit_reason)
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
        "previousByDimension": {k: to_camel_dict(v) for k, v in payload.previous_by_dimension.items()},
        "stalePreviousByDimension": {k: to_camel_dict(v) for k, v in payload.stale_previous_by_dimension.items()},
        "staleDimensions": [to_camel_dict(d) for d in payload.stale_dimensions],
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
    # Status-aware fetcher: bypass cache for in_progress runs whose on-disk
    # evaluation/*.json set grows as dims finish mid-run. Without this,
    # the History page renders the partial dim set from the first read
    # forever -- new dims that complete later never surface.
    get_run_dimensions = _make_status_aware_fetcher(
        reports_root, project, history_runs,
        cache=cc.cache, lock=cc.lock, max_size=cc.max_size,
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


def _apply_sql_grade_override(
    reports_root: Path,
    project: str,
    run_id: str,
    payload: _DashboardPayload,
) -> _DashboardPayload:
    """Override per-dimension grade fields from SQL grade tables when available.

    Keeps the dashboard rollup in lockstep with dim-detail dismisses: a
    dismiss updates SQL via the projection layer, the next dashboard read
    reflects the new scores. Safe to overlay because the SQL projector
    now applies the same confidence-level Insufficient rule the CLI
    engine uses (see ``services.scoring.projector_scoring`` +
    ``core.evidence.model.classify_confidence_level``) — SQL grades and
    JSON grades agree on the same input.

    Falls back to the FS-based grades when grade tables are empty or the
    run directory does not exist.
    """
    import sqlite3  # noqa: PLC0415

    from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository  # noqa: PLC0415
    from quodeq.data.sqlite.state_store import SQLiteStateStore  # noqa: PLC0415

    run_dir = reports_root / project / run_id
    if not run_dir.is_dir():
        return payload

    store = SQLiteStateStore(run_dir)
    try:
        repo = SqliteFindingsRepository(run_dir)
        repo._ensure_fresh()  # noqa: SLF001
        dim_rows = store.read_dimension_scores()
    except sqlite3.DatabaseError:
        # evaluation.db is unreadable by this binary: written by a newer Quodeq
        # (SchemaVersionError, a DatabaseError subclass) or otherwise corrupt /
        # half-written. Keep the FS-based grades already in the payload rather
        # than crashing the build.
        _logger.warning(
            "evaluation.db for %s/%s is unreadable; keeping FS-based grades "
            "in the dashboard.", project, run_id,
        )
        return payload
    if not dim_rows:
        return payload

    sql_grades: dict[str, dict] = {r["dimension"]: r for r in dim_rows}

    def _override_dim(d: DimensionResult) -> DimensionResult:
        row = sql_grades.get(d.dimension)
        if row is None:
            return d
        score_val: float | None = row.get("score")
        sql_score = f"{score_val}/10" if score_val is not None else d.overall_score
        sql_grade = row.get("grade") or d.overall_grade
        return replace(d, overall_score=sql_score, overall_grade=sql_grade)

    overridden_dims = [_override_dim(d) for d in payload.dimensions_with_trend]

    run_score = store.read_run_score_from_dim_scores()
    if run_score.get("grade") is not None:
        sql_numeric_avg: float | None = run_score.get("score")
        sql_run_grade: str | None = run_score.get("grade")
        overridden_summary = replace(
            payload.selected_summary,
            overall_grade=sql_run_grade,
            numeric_average=sql_numeric_avg,
        )
    else:
        overridden_summary = payload.selected_summary

    payload.dimensions_with_trend = overridden_dims
    payload.selected_summary = overridden_summary
    return payload


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
    payload = _apply_sql_grade_override(reports_root, project, selected_run.run_id, payload)
    exit_reason = _read_run_exit_reason(reports_root, project, selected_run.run_id)
    return _build_dashboard_result(
        project, runs, selected_run, payload, exit_reason=exit_reason,
    )
