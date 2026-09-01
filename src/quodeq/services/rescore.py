"""Live rescore service -- recalculates grades after dismissals change.

Split (Task 12) into this dispatcher/public-API module plus
_rescore_legacy.py, which holds the in-place scoring fallback used when a
run has no evidence basis to rescore from.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from quodeq.core.types import DimensionResult
from quodeq.shared.serialization import to_camel_dict
from quodeq.core.types.finding import Finding
from quodeq.core.types.report import PrincipleGrade
from quodeq.core.scoring.overall import weighted_overall, MODE_NUMERICAL
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.data.fs.report_parser.grades import summarize_dimensions
from quodeq.services import grade_formula
from quodeq.services._rescore_legacy import _group_by_principle, _score_all_principles
from quodeq.services.dismissed import recount_totals
from quodeq.services.evidence_rescore import score_dimension_from_evidence
from quodeq.services.suppression import is_deleted, is_dismissed


def _filter_excluded_violations(
    dim: DimensionResult, dismissed: set[tuple], deleted: set[tuple], rules: tuple,
) -> list[Finding]:
    """Violations minus anything dismissed or deleted."""
    dim_id = dim.dimension or ""
    return [
        v for v in dim.violations
        if not is_dismissed(dismissed, req=v.req, principle=v.practice_id, rules=rules,
                            file=v.file, line=v.line)
        and not is_deleted(deleted, dimension=dim_id, principle=v.practice_id, file=v.file)
    ]


def _rescore_from_evidence(
    dim: DimensionResult, filtered_violations: list[Finding],
    dismissed: set[tuple], deleted: set[tuple],
    run_dir: Path, params: ScoringParams, compliance_count: int,
) -> DimensionResult | None:
    """Recompute a dimension's score from its run evidence (single scoring
    basis, shared with the scan-time engine). Returns None when the run has
    no evidence for this dimension -- callers fall back to the legacy path."""
    dim_id = dim.dimension or ""
    scores = score_dimension_from_evidence(
        run_dir, dim_id, dismissed=dismissed, deleted=deleted,
        source_file_count=dim.source_file_count or 0,
        files_read=dim.files_read or 0, params=params,
    )
    if scores is None:
        return None
    principle_grades = [
        PrincipleGrade(
            principle=ps.display_name,
            score=(f"{ps.final_score}/10" if ps.final_score is not None else None),
            grade=ps.grade,
        )
        for ps in scores.principles.values()
    ]
    overall = scores.overall
    return replace(
        dim,
        violations=filtered_violations,
        principles=principle_grades,
        overall_score=(f"{overall.weighted_score}/10"
                       if overall.weighted_score is not None else None),
        overall_grade=overall.grade or overall.weighted_grade,
        totals=recount_totals(filtered_violations, compliance_count=compliance_count),
    )


def _rescore_legacy_fallback(
    dim: DimensionResult, filtered_violations: list[Finding],
    params: ScoringParams, compliance_count: int,
) -> DimensionResult:
    """In-place rescore for a run/dimension with no evidence basis."""
    principles_violations = _group_by_principle(filtered_violations)
    principles_compliance = _group_by_principle(dim.compliance)
    principle_scores, principle_grades = _score_all_principles(
        principles_violations, principles_compliance,
        source_file_count=dim.source_file_count or 0,
        params=params,
    )

    overall = weighted_overall(principle_scores, MODE_NUMERICAL, params)
    overall_score_str = f"{overall.weighted_score}/10" if overall.weighted_score is not None else None
    overall_grade = overall.grade or overall.weighted_grade

    new_totals = recount_totals(filtered_violations, compliance_count=compliance_count)

    return replace(
        dim,
        violations=filtered_violations,
        principles=principle_grades,
        overall_score=overall_score_str,
        overall_grade=overall_grade,
        totals=new_totals,
    )


def _rescore_dimension(
    dim: DimensionResult,
    dismissed: set[tuple],
    deleted: set[tuple] | None = None,
    params: ScoringParams = DEFAULT_PARAMS,
    *,
    run_dir: Path | None = None,
    rules: tuple = (),
) -> DimensionResult:
    """Rescore a single dimension after filtering dismissed and deleted findings.

    When *run_dir* is given and the run still has `<dim>_evidence.jsonl`, the
    score is recomputed by the scan-time engine over the evidence minus the
    excluded findings (single scoring basis). The legacy in-place formula
    (_rescore_legacy_fallback) is only a fallback for runs without evidence.
    """
    deleted = deleted or set()
    filtered_violations = _filter_excluded_violations(dim, dismissed, deleted, rules)
    if len(filtered_violations) == len(dim.violations):
        return dim

    compliance_count = dim.totals.compliance_count if dim.totals else len(dim.compliance)

    if run_dir is not None:
        rescored = _rescore_from_evidence(
            dim, filtered_violations, dismissed, deleted, run_dir, params, compliance_count,
        )
        if rescored is not None:
            return rescored

    return _rescore_legacy_fallback(dim, filtered_violations, params, compliance_count)


def rescore_dimensions(
    dimensions: list[DimensionResult],
    dismissed_keys: set[tuple],
    deleted_keys: set[tuple] | None = None,
    params: ScoringParams | None = None,
    *,
    run_dir: Path | None = None,
    rules: tuple = (),
) -> dict[str, Any]:
    """Rescore all dimensions after filtering dismissed and deleted findings.

    Returns a dict with 'dimensions' (list of camelCase dicts) and 'summary' (camelCase dict).
    When *params* is None, the saved grade-formula params are loaded. When
    *run_dir* is given, each touched dimension is rescored from that run's
    evidence when available (see `_rescore_dimension`).
    """
    if params is None:
        params = grade_formula.load_params()
    rescored = [
        _rescore_dimension(dim, dismissed_keys, deleted_keys, params=params,
                           run_dir=run_dir, rules=rules)
        for dim in dimensions
    ]
    summary = summarize_dimensions(rescored, params=params)
    return {
        "dimensions": [to_camel_dict(d) for d in rescored],
        "summary": to_camel_dict(summary),
    }
