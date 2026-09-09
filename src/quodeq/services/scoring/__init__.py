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

from pathlib import Path
from typing import Any, Callable

from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.types.dimension import DimensionResult
from quodeq.services._trend_fetcher import make_rescoring_fetcher
from quodeq.services.dashboard import _make_run_dimension_fetcher
from quodeq.services.grade_formula import load_params
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services._wiring import read_run_data
from quodeq.services.rescore import _rescore_dimension
from quodeq.shared.validation import validate_path_segment
from quodeq.services.scoring._summary import recompute_summary  # noqa: F401 — facade re-export

# ---------------------------------------------------------------------------
# Decomposed submodules. Every moved name is re-exported here so external
# callers and test patch targets keep working against the package facade.
# ---------------------------------------------------------------------------
from quodeq.services.scoring._deps import ScoringDeps, _NO_DEPS  # noqa: F401
from quodeq.services.scoring._fetchers import _make_trend_fetcher, _max_history_runs  # noqa: F401
from quodeq.services.scoring._response_builders import (  # noqa: F401
    _build_dimension_dict,
    _build_response_from_eval_files,
    _build_response_from_grade_tables,
    _build_summary_from_dim_dicts,
    _build_totals_from_findings,
    _severity_bucket,
)
from quodeq.services.scoring._rescoring import (  # noqa: F401
    _dims_expecting_rescore,
    _merge_rescored_dims,
    _rescore_accumulated_response,
    _rescore_accumulated_with_coverage,
    _rescore_runs_by_dimension,
)
from quodeq.services.scoring._project_scores import get_project_scores  # noqa: F401
from quodeq.services.scoring._scores_raw import get_scores_raw, get_scores_slim  # noqa: F401
from quodeq.services._wiring import load_suppression_rules


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


__all__ = [
    "get_scores_raw",
    "get_scores_slim",
    "get_project_scores",
    "scored_run_dimensions",
]
