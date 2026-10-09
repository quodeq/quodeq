"""Live rescore service -- recalculates grades after dismissals change.

This is the dispatcher/public-API module; _rescore_legacy.py holds the in-place scoring fallback used when a
run has no evidence basis to rescore from.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from quodeq.core.types import DimensionResult, OverallScore
from quodeq.shared.serialization import to_camel_dict
from quodeq.core.types.finding import Finding
from quodeq.core.types.report import PrincipleGrade
from quodeq.core.scoring.overall import weighted_overall, MODE_NUMERICAL
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.scoring.report_grades import summarize_dimensions
from quodeq.services import grade_formula
from quodeq.services._rescore_legacy import group_by_principle, score_all_principles
from quodeq.services.dismissed import recount_totals
from quodeq.services.evidence_rescore import (
    EvidenceScoreRequest, score_dimension_from_evidence, standard_dirs,
)
from quodeq.services.suppression import FindingRef, is_deleted, is_dismissed
from quodeq.services.severity_classes import load_severity_classes_for_run
from quodeq.services.suppression_keys import SuppressionKeys


def filter_excluded_violations(dim: DimensionResult, keys: SuppressionKeys) -> list[Finding]:
    """Violations minus anything dismissed or deleted."""
    dim_id = dim.dimension or ""
    return [
        v for v in dim.violations
        if not is_dismissed(keys.dismissed, FindingRef(
            req=v.req, principle=v.practice_id, file=v.file, line=v.line,
            snippet=v.snippet), rules=keys.rules)
        and not is_deleted(keys.deleted, dimension=dim_id, principle=v.practice_id, file=v.file)
    ]


def _compliance_count(dim: DimensionResult) -> int:
    return dim.totals.compliance_count if dim.totals else len(dim.compliance)


def _rescored(
    dim: DimensionResult, filtered_violations: list[Finding],
    principle_grades: list[PrincipleGrade], overall: OverallScore,
) -> DimensionResult:
    """*dim* carrying the filtered violations, the new principle grades, the
    overall score and grade from *overall*, and recounted totals.

    Takes *principle_grades* and *overall* as already-computed inputs, so
    any caller can rescore *dim* regardless of how those were derived.
    """
    return replace(
        dim,
        violations=filtered_violations,
        principles=principle_grades,
        overall_score=(f"{overall.weighted_score}/10"
                       if overall.weighted_score is not None else None),
        overall_grade=overall.grade or overall.weighted_grade,
        totals=recount_totals(filtered_violations, compliance_count=_compliance_count(dim),
                              files_read=dim.files_read),
    )


def _rescore_from_evidence(
    dim: DimensionResult, filtered_violations: list[Finding],
    keys: SuppressionKeys, run_dir: Path, params: ScoringParams,
    classes: Mapping[str, str],
) -> DimensionResult | None:
    """Recompute a dimension's score from its run evidence (single scoring
    basis, shared with the scan-time engine). Returns None when the run has
    no evidence for this dimension -- callers fall back to the legacy path."""
    dim_id = dim.dimension or ""
    scores = score_dimension_from_evidence(
        run_dir, dim_id, EvidenceScoreRequest(
            dismissed=keys.dismissed, deleted=keys.deleted,
            source_file_count=dim.source_file_count or 0,
            files_read=dim.files_read or 0, params=params,
            standard_dirs_fn=standard_dirs, classes=classes,
        ),
    )
    if scores is None:
        return None
    principle_grades = [
        PrincipleGrade(
            principle=ps.display_name,
            score=(f"{ps.final_score}/10" if ps.final_score is not None else None),
            grade=ps.grade,
            confidence=ps.confidence_level,
        )
        for ps in scores.principles.values()
    ]
    return _rescored(dim, filtered_violations, principle_grades, scores.overall)


def _rescore_legacy_fallback(
    dim: DimensionResult, filtered_violations: list[Finding], params: ScoringParams,
    classes: Mapping[str, str],
) -> DimensionResult:
    """In-place rescore for a run/dimension with no evidence basis."""
    principles_violations = group_by_principle(filtered_violations)
    principles_compliance = group_by_principle(dim.compliance)
    principle_scores, principle_grades = score_all_principles(
        principles_violations, principles_compliance,
        source_file_count=dim.source_file_count or 0,
        params=params, classes=classes,
    )

    overall = weighted_overall(principle_scores, MODE_NUMERICAL, params)
    return _rescored(dim, filtered_violations, principle_grades, overall)


def rescore_dimension(
    dim: DimensionResult,
    keys: SuppressionKeys,
    params: ScoringParams = DEFAULT_PARAMS,
    *,
    run_dir: Path | None = None,
) -> DimensionResult:
    """Rescore a single dimension after filtering the findings *keys* suppress.

    When *run_dir* is given and the run still has `<dim>_evidence.jsonl`, the
    score is recomputed by the scan-time engine over the evidence minus the
    excluded findings (single scoring basis). The legacy in-place formula
    (_rescore_legacy_fallback) is only a fallback for runs without evidence.
    """
    filtered_violations = filter_excluded_violations(dim, keys)
    if len(filtered_violations) == len(dim.violations):
        return dim

    classes = load_severity_classes_for_run(run_dir) if run_dir is not None else {}
    if run_dir is not None:
        rescored = _rescore_from_evidence(
            dim, filtered_violations, keys, run_dir, params, classes)
        if rescored is not None:
            return rescored

    return _rescore_legacy_fallback(dim, filtered_violations, params, classes)


def with_hidden_counts(
    raw: DimensionResult, shown: DimensionResult, keys: SuppressionKeys,
) -> DimensionResult:
    """*shown* annotated with how many of *raw*'s violations *keys* hid.

    ``suppressed_count`` is the whole gap between what the scan found and what
    *shown* carries, the total the UI reports. ``dismissed_count`` is the share
    the dismissed filter alone (dismissals and rules) accounts for; deletions
    suppress a principle across a file and accumulate over many runs, so the
    two differ sharply on projects with a triage history. *shown* is returned
    as is when nothing was hidden: the counts stay None and the serialized
    dimension omits the keys.
    """
    hidden = len(raw.violations) - len(shown.violations)
    if hidden <= 0:
        return shown
    dismissed_only = SuppressionKeys(keys.dismissed, frozenset(), keys.rules)
    dismissed = len(raw.violations) - len(filter_excluded_violations(raw, dismissed_only))
    return replace(shown, dismissed_count=dismissed or None, suppressed_count=hidden)


def rescore_dimensions(
    dimensions: list[DimensionResult],
    keys: SuppressionKeys,
    params: ScoringParams | None = None,
    *,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    """Rescore all dimensions after filtering the findings *keys* suppress.

    Returns a dict with 'dimensions' (list of camelCase dicts) and 'summary' (camelCase dict).
    When *params* is None, the saved grade-formula params are loaded. When
    *run_dir* is given, each touched dimension is rescored from that run's
    evidence when available (see `rescore_dimension`).
    """
    if params is None:
        params = grade_formula.load_params()
    rescored = [
        rescore_dimension(dim, keys, params=params, run_dir=run_dir)
        for dim in dimensions
    ]
    summary = summarize_dimensions(rescored, params=params)
    return {
        "dimensions": [to_camel_dict(d) for d in rescored],
        "summary": to_camel_dict(summary),
    }
