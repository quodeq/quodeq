"""Scoring reader — single read-side entry point for all score data.

Hides the chain of underlying steps (run-dimension fetch, dismissal/deletion
filter, rescore, accumulated aggregation, trend build, summary recompute)
behind a 2-method interface. External callers should never reach into the
private helpers in this package.

Public API
----------
- ``get_scores_raw(reports_root, project, run_id)`` -- rescored dimensions
  and summary for a single run (Explorer detail).
- ``get_project_scores(reports_root, project, as_of)`` -- full dashboard
  payload: accumulated dimensions, summary, trend, available runs.

All functions apply dismissals/deletions server-side and return the same
data shapes as the existing endpoints, so the frontend sees no schema
change.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

_logger = logging.getLogger(__name__)

from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.types.dimension import DimensionResult
from quodeq.services._dashboard_trend import build_accumulated_trend
from quodeq.services._trend_fetcher import make_rescoring_fetcher, make_trend_fetcher
from quodeq.services.accumulated import compute_accumulated
from quodeq.services.dashboard import _make_run_dimension_fetcher
from quodeq.services.grade_formula import is_custom, load_params
from quodeq.services.ports import StoreUnreadableError
from quodeq.services.scoring_view import select_trend_runs
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.score_cache import (
    accumulated_cache_version,
    cached_accumulated,
    per_run_versions,
)
from quodeq.services._wiring import (
    RunInfo,
    find_children,
    list_runs,
    read_run_data,
    read_run_scalars,
)
from quodeq.services.rescore import _rescore_dimension
from quodeq.shared._env import env_int
from quodeq.shared.validation import validate_path_segment
from quodeq.services.scoring._summary import recompute_summary  # noqa: F401 — facade re-export

# ---------------------------------------------------------------------------
# Decomposed submodules. Every moved name is re-exported here so external
# callers and test patch targets keep working against the package facade.
# ---------------------------------------------------------------------------
from quodeq.services.scoring._deps import ScoringDeps, _NO_DEPS  # noqa: F401
from quodeq.services.scoring._response_builders import (  # noqa: F401
    _build_dimension_dict,
    _build_response_from_eval_files,
    _build_response_from_grade_tables,
    _build_summary_from_dim_dicts,
    _build_totals_from_findings,
    _severity_bucket,
)
from quodeq.services._wiring import (
    SQLiteStateStore,
    SqliteFindingsRepository,
    load_suppression_rules,
)
from quodeq.services.scoring._rescoring import (  # noqa: F401
    _dims_expecting_rescore,
    _merge_rescored_dims,
    _rescore_accumulated_response,
    _rescore_accumulated_with_coverage,
    _rescore_runs_by_dimension,
)

def _max_history_runs() -> int:
    """Read max history runs from env at call time for lazy configuration."""
    return env_int("QUODEQ_MAX_HISTORY_RUNS", 100, minimum=1)


# ---------------------------------------------------------------------------
# SQL-backed response builder
# ---------------------------------------------------------------------------

def get_scores_raw(
    reports_root: Path, project: str, run_id: str,
    deps: ScoringDeps | None = None,
) -> dict:
    """Return raw rescore dict for a single run (explorer detail compat).

    Tries SQL grade tables first (fast path for runs projected from
    events.jsonl). Falls back to reading the eval JSON files + applying
    rescore when SQL is empty — this is the case for older runs that
    pre-date the event-log scoring engine. Without this fallback, ~all
    pre-event-log runs returned an empty ``{dimensions: [], summary: {}}``
    payload, which made live-grade updates impossible for them: the dismiss
    POST returned no scores, the UI had nothing to apply.
    """
    validate_path_segment(project, run_id)
    d = deps or _NO_DEPS
    run_dir = reports_root / project / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    params = load_params()

    # The SQL grade tables are frozen per run and, on a stale projection,
    # reflect only the dismissals already projected into THIS run's own findings
    # table -- NOT project-wide dismissals/deletions that accrued later. So when
    # the project has active dismissals/deletions AND this run has eval JSON to
    # rescore from, defer to the eval-file path, which applies the project-wide
    # dismiss set authoritatively via ``rescore_dimensions`` -- the SAME
    # transform the accumulated view uses, so every per-run read agrees on the
    # dismiss-adjusted score. Event-log-only runs (no eval JSON) can't be
    # rescored that way; they keep the SQL path, whose ``_ensure_fresh``
    # re-projection applies the dismissals directly to the findings table.
    project_dir = reports_root / project
    has_project_wide_filters = bool(
        (d.dismissed_keys or dismissed_keys)(project_dir)
        or (d.deleted_keys or deleted_keys)(project_dir)
    )
    eval_dir = run_dir / "evaluation"
    prefer_eval_rescore = (
        has_project_wide_filters
        and eval_dir.is_dir()
        and any(p.suffix == ".json" for p in eval_dir.iterdir())
    )

    # SQL path is meaningful only when events.jsonl exists. For older runs
    # without one, skip straight to the JSON-file fallback so we don't have
    # to wait on a no-op projection that will leave the grade tables empty.
    if not prefer_eval_rescore and (run_dir / "events.jsonl").is_file():
        try:
            repo = (d.findings_repo_factory or SqliteFindingsRepository)(run_dir)
            repo.ensure_projected()
            store_factory = d.grade_tables_factory or SQLiteStateStore
            store = store_factory(run_dir)
            if store.read_dimension_scores():
                return _build_response_from_grade_tables(
                    run_dir, params=params, store_factory=store_factory,
                )
        except StoreUnreadableError:
            # evaluation.db is unreadable by this binary: it was written by a
            # newer Quodeq (SchemaVersionError, a DatabaseError subclass) or is
            # otherwise corrupt/half-written. Don't crash the score read; fall
            # back to the JSON eval files (schema-independent) so a downgraded
            # or upgrading install still works.
            _logger.warning(
                "Run %s/%s has an unreadable evaluation.db; serving scores "
                "from the JSON eval files instead of the SQL grade tables.",
                project, run_id,
            )

    return _build_response_from_eval_files(
        reports_root, project, run_id, params=params, deps=deps,
    )


def get_scores_slim(
    reports_root: Path, project: str, run_id: str,
    deps: ScoringDeps | None = None,
) -> dict:
    """``get_scores_raw`` with finding bodies stripped for the run-scores route.

    The Explorer (the endpoint's only consumer) uses the response to overlay
    dismissal-aware scores onto the eval payload it fetched separately: it
    reads per-dimension/per-principle score + grade + totals, and uses each
    violation solely as a ``req|file|line`` identity key to filter dismissed
    findings out of the eval data. Returning full bodies made the response
    7+ MB on finding-heavy runs; the slim form carries the same information
    the merge needs at a fraction of the size. Compliance bodies are never
    read from this payload, so the list is emptied (counts live in totals).
    """
    raw = get_scores_raw(reports_root, project, run_id, deps=deps)
    slim_dims = []
    for dim in raw.get("dimensions", []) or []:
        slim_violations = [
            {"req": v.get("req"), "file": v.get("file"), "line": v.get("line")}
            for v in (dim.get("violations") or [])
        ]
        slim_dims.append({**dim, "violations": slim_violations, "compliance": []})
    return {**raw, "dimensions": slim_dims}


def scored_run_dimensions(
    reports_root: Path, project: str, run_id: str,
    params: ScoringParams | None = None,
    deps: ScoringDeps | None = None,
) -> list[DimensionResult]:
    """Return a run's dimensions with the project-wide dismiss/delete rescore applied.

    This is the single seam every per-run read path routes through so the SAME
    run+dimension reports the SAME score everywhere. It is
    ``read_run_data`` (raw, dismissals NOT applied) composed with the same
    project-wide ``_rescore_dimension`` the accumulated view already runs, and
    returns ``DimensionResult`` objects (not camelCase dicts).

    Rescore is deliberately kept *out* of ``read_run_data`` itself: that
    function is foundational and feeds exports and other callers that must see
    the raw scan. Callers that want the dismiss-adjusted view ask for it here.

    When *params* is None the saved grade-formula params are loaded, matching
    ``get_scores_raw`` / ``build_dashboard``.
    """
    validate_path_segment(project, run_id)
    d = deps or _NO_DEPS
    if params is None:
        params = load_params()
    project_dir = reports_root / project
    dismissed = (d.dismissed_keys or dismissed_keys)(project_dir)
    deleted = (d.deleted_keys or deleted_keys)(project_dir)
    dims = (d.read_run_data or read_run_data)(reports_root, project, run_id)
    rules = load_suppression_rules(project_dir)
    # Rules are suppression state too: skipping the rescore when only rules
    # exist would silently return raw scores for a project whose ADRs are
    # expressed as patterns rather than per-line dismissals.
    if not dismissed and not deleted and not rules:
        return dims
    run_dir = project_dir / run_id
    rescore = d.rescore_dimension or _rescore_dimension
    return [
        rescore(dim, dismissed, deleted, params=params, run_dir=run_dir, rules=rules)
        for dim in dims
    ]


def _make_rescoring_fetcher(
    reports_root: Path, project: str,
    params: ScoringParams = DEFAULT_PARAMS,
    deps: ScoringDeps | None = None,
) -> Callable[[str], list[DimensionResult]]:
    """Return a dimension fetcher that applies rescore (dismissals) to results.

    Thin seam over the shared :func:`make_rescoring_fetcher` factory. The
    suppression readers come from *deps* (production defaults when None),
    plus the full-data base fetcher.
    """
    d = deps or _NO_DEPS
    return make_rescoring_fetcher(
        reports_root, project, params=params,
        base_fetcher=_make_run_dimension_fetcher(reports_root, project),
        dismissed_keys=d.dismissed_keys or dismissed_keys,
        deleted_keys=d.deleted_keys or deleted_keys,
    )


def _make_trend_fetcher(
    reports_root: Path, project: str,
    params: ScoringParams = DEFAULT_PARAMS,
    cacheable_run_ids: set[str] | None = None,
    deps: ScoringDeps | None = None,
) -> Callable[[str], list[DimensionResult]]:
    """Return the dimension fetcher for the trend chart.

    Thin seam over the shared :func:`make_trend_fetcher` factory. The scalar
    reader and suppression readers come from *deps* (production defaults
    when None), plus the shared full-data base-fetcher factory. See
    :func:`make_trend_fetcher` for the fast/heavy path and caching semantics.
    """
    d = deps or _NO_DEPS
    return make_trend_fetcher(
        reports_root, project, params=params, cacheable_run_ids=cacheable_run_ids,
        max_history=_max_history_runs(),
        base_fetcher_factory=_make_run_dimension_fetcher,
        read_run_scalars=d.read_run_scalars or read_run_scalars,
        dismissed_keys=d.dismissed_keys or dismissed_keys,
        deleted_keys=d.deleted_keys or deleted_keys,
    )


def rescore_accumulated(
    accumulated: dict[str, Any] | None,
    reports_root: Path, project: str,
    params: ScoringParams | None = None,
    deps: ScoringDeps | None = None,
) -> dict[str, Any] | None:
    """Public seam: project-wide dismiss/delete rescore for an accumulated payload.

    Callers that read ``compute_accumulated`` directly (rather than through
    ``get_project_scores``) get scores that ignore dismissals/deletions --
    ``filter_dismissed_from_dimensions`` drops the violations but leaves the
    baked scores untouched. Route the payload through here so every consumer
    reports the same dismiss-adjusted score as the Overview. No-op when the
    project has no active dismissals or deletions.

    When *params* is None the saved grade-formula params are loaded, matching
    ``get_project_scores``.
    """
    if not accumulated:
        return accumulated
    if params is None:
        params = load_params()
    return _rescore_accumulated_response(
        accumulated, reports_root, project, params=params, deps=deps,
    )


def get_project_scores(
    reports_root: Path, project: str, as_of: str | None = None,
    deps: ScoringDeps | None = None,
) -> dict[str, Any] | None:
    """Return the full scores payload for the dashboard.

    Returns a dict with:
      - accumulated: { dimensions, summary } (same shape as /accumulated endpoint)
      - trend: [{ runId, dateISO, ... }] (same shape as dashboard.trend)
      - availableRuns: [{ runId, dateLabel }]

    All scores have dismissals applied server-side.
    """
    if not (reports_root / project).exists():
        return None

    d = deps or _NO_DEPS
    params = load_params()

    # How the numbers were produced, not what they are. A tuned formula moves
    # every score at once and leaves no other trace -- findings and runs are
    # unchanged -- so the Overview has to be able to say so next to the grade.
    # Computed outside the accumulated cache: it is a file-existence check, and
    # keeping it out of the cached payload avoids another version input.
    scoring_meta = {"customFormula": (d.is_custom_formula or is_custom)()}

    all_runs = list_runs(reports_root, project)
    if not all_runs:
        return {
            "accumulated": {"dimensions": [], "summary": {}},
            "trend": [],
            "availableRuns": [],
            "scoring": scoring_meta,
        }

    # Build accumulated using the existing service (returns full data with
    # violations). The rescore-coverage flag rides in a cell so the cacheable
    # gate below can see it: a payload whose rescore missed dimensions must be
    # served but never persisted (its version hash can't self-invalidate).
    rescore_complete = [True]

    def _compute_accumulated_payload() -> dict:
        acc = compute_accumulated(str(reports_root), project, as_of, params=params)
        if acc is None:
            acc = {"dimensions": [], "summary": {}}
        payload, complete = _rescore_accumulated_with_coverage(
            acc, reports_root, project, params=params, deps=deps,
        )
        rescore_complete[0] = complete
        return payload

    if find_children(reports_root, project):
        # Parent aggregation pulls child projects' dismissals/runs into the
        # payload, which the project-scoped cache version can't see -- bypass
        # the cache for parents to avoid serving stale data.
        accumulated = _compute_accumulated_payload()
    else:
        acc_version = accumulated_cache_version(
            reports_root / project, params,
            per_run_versions(reports_root / project, project, params,
                             [(r.run_id, r.status) for r in all_runs]),
            as_of,
        )
        accumulated = (d.cached_accumulated or cached_accumulated)(
            project, acc_version, _compute_accumulated_payload,
            cacheable=lambda _payload: rescore_complete[0],
        )

    # Build trend using the appropriate fetcher: scalar fast path when there
    # are no active dismissals/deletions, rescoring (findings) path otherwise.
    # Shared trend rule (scoring_view.select_trend_runs): cancelled/failed
    # runs are excluded — their partial scores are misleading on the history
    # chart. They remain in availableRuns so the UI can show them when the
    # user asks for them explicitly.
    scoreable_runs = select_trend_runs(all_runs)
    history_runs = scoreable_runs[:_max_history_runs()]
    # Only completed runs may be persisted to the score cache: an in-progress
    # run's scalar set is still growing, and the cache version can't see that,
    # so caching its partial set would strand a stale row (e.g. 1 of 6 dims)
    # served forever after the run finishes.
    cacheable_run_ids = {r.run_id for r in history_runs if r.status == "complete"}
    trend_fetcher = _make_trend_fetcher(
        reports_root, project, params=params, cacheable_run_ids=cacheable_run_ids,
        deps=deps,
    )
    trend = build_accumulated_trend(history_runs, trend_fetcher, params=params)

    # Build available runs list
    available_runs = [
        {"runId": r.run_id, "dateLabel": r.date_label, "status": r.status}
        for r in all_runs
    ]

    return {
        "accumulated": accumulated,
        "trend": trend,
        "availableRuns": available_runs,
        "scoring": scoring_meta,
    }


__all__ = [
    "get_scores_raw",
    "get_scores_slim",
    "get_project_scores",
    "scored_run_dimensions",
]
