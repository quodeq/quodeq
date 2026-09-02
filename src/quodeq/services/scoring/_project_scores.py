"""Full dashboard scores payload: accumulated + trend + available runs.

Split from ``scoring/__init__.py`` to keep that file under the size
ratchet's 300-line cap. ``get_project_scores`` stays re-exported from there.
Imported at the bottom of that file (after ``_max_history_runs`` and
``_make_trend_fetcher`` are already defined there), so the
``from quodeq.services.scoring import ...`` below resolves against the
already-initialized part of that (still-loading) module; no true cycle.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.core.scoring.params import ScoringParams
from quodeq.services._dashboard_trend import build_accumulated_trend
from quodeq.services.accumulated import compute_accumulated
from quodeq.services.grade_formula import is_custom, load_params
from quodeq.services.scoring_view import select_trend_runs
from quodeq.services.score_cache import (
    accumulated_cache_version,
    cached_accumulated,
    per_run_versions,
)
from quodeq.services._wiring import find_children, list_runs
from quodeq.services.scoring._deps import ScoringDeps, _NO_DEPS
from quodeq.services.scoring._rescoring import _rescore_accumulated_with_coverage
from quodeq.services.scoring import _make_trend_fetcher, _max_history_runs


def _compute_accumulated_payload(
    reports_root: Path, project: str, as_of: str | None, params: ScoringParams,
    deps: ScoringDeps | None, rescore_complete: list[bool],
) -> dict:
    """Compute accumulated dims + summary, rescored, tracking coverage in
    *rescore_complete* (a 1-element list used as an outparam) so the caller's
    cache-eligibility check can see it."""
    acc = compute_accumulated(str(reports_root), project, as_of, params=params)
    if acc is None:
        acc = {"dimensions": [], "summary": {}}
    payload, complete = _rescore_accumulated_with_coverage(
        acc, reports_root, project, params=params, deps=deps,
    )
    rescore_complete[0] = complete
    return payload


def _resolve_accumulated(
    reports_root: Path, project: str, as_of: str | None, params: ScoringParams,
    deps: ScoringDeps, all_runs: list, rescore_complete: list[bool],
) -> dict:
    """Compute (or fetch from cache) the accumulated dims + summary."""
    if find_children(reports_root, project):
        # Parent aggregation pulls child projects' dismissals/runs into the
        # payload, which the project-scoped cache version can't see -- bypass
        # the cache for parents to avoid serving stale data.
        return _compute_accumulated_payload(reports_root, project, as_of, params, deps, rescore_complete)
    acc_version = accumulated_cache_version(
        reports_root / project, params,
        per_run_versions(reports_root / project, project, params,
                         [(r.run_id, r.status) for r in all_runs]),
        as_of,
    )
    return (deps.cached_accumulated or cached_accumulated)(
        project, acc_version,
        lambda: _compute_accumulated_payload(reports_root, project, as_of, params, deps, rescore_complete),
        cacheable=lambda _payload: rescore_complete[0],
    )


def _resolve_trend(
    reports_root: Path, project: str, params: ScoringParams,
    deps: ScoringDeps | None, all_runs: list,
) -> list[dict]:
    """Build trend using the appropriate fetcher: scalar fast path when there
    are no active dismissals/deletions, rescoring (findings) path otherwise.
    Shared trend rule (scoring_view.select_trend_runs): cancelled/failed
    runs are excluded — their partial scores are misleading on the history
    chart. They remain in availableRuns so the UI can show them when the
    user asks for them explicitly."""
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
    return build_accumulated_trend(history_runs, trend_fetcher, params=params)


def _empty_project_scores(scoring_meta: dict) -> dict[str, Any]:
    return {
        "accumulated": {"dimensions": [], "summary": {}},
        "trend": [],
        "availableRuns": [],
        "scoring": scoring_meta,
    }


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
        return _empty_project_scores(scoring_meta)

    # The rescore-coverage flag rides in a cell so the cacheable gate can see
    # it: a payload whose rescore missed dimensions must be served but never
    # persisted (its version hash can't self-invalidate).
    rescore_complete = [True]
    accumulated = _resolve_accumulated(reports_root, project, as_of, params, d, all_runs, rescore_complete)
    trend = _resolve_trend(reports_root, project, params, deps, all_runs)

    return {
        "accumulated": accumulated,
        "trend": trend,
        "availableRuns": [
            {"runId": r.run_id, "dateLabel": r.date_label, "status": r.status}
            for r in all_runs
        ],
        "scoring": scoring_meta,
    }
