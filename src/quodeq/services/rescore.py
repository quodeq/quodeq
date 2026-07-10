"""Live rescore service -- recalculates grades after dismissals change."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from quodeq.core.types import DimensionResult, to_camel_dict
from quodeq.core.types.finding import Finding
from quodeq.core.types.report import PrincipleGrade
from quodeq.core.scoring.engine import compute_tallies
from quodeq.core.scoring.internals import (
    violation_base,
    compliance_lift,
    violation_ceiling,
    severity_grade_floor,
    score_to_grade_label,
)
from quodeq.core.scoring.overall import weighted_overall, MODE_NUMERICAL
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.types.scoring import PrincipleScore
from quodeq.data.fs.report_parser.grades import summarize_dimensions
from quodeq.services.dismissed import recount_totals


def _finding_to_dict(f: Finding) -> dict[str, Any]:
    """Convert a Finding dataclass to the dict format scoring internals expect.

    Only includes 'vt' when the finding has an explicit violation_type, so
    ``evidence_has_taxonomy()`` selects the same mode (taxonomy vs reason)
    that the original evaluation used.
    """
    d: dict[str, Any] = {
        "severity": f.severity or "minor",
        "reason": f.reason or "",
    }
    if f.violation_type:
        d["vt"] = f.violation_type
    return d


def _score_principle(
    violations: list[Finding], compliance: list[Finding],
    *, source_file_count: int = 0, scale_multiplier: int = 1,
    params: ScoringParams = DEFAULT_PARAMS,
) -> tuple[float | None, str]:
    """Score a single principle from its filtered violations and compliance lists.

    Applies the same confidence-level Insufficient rule the CLI engine
    uses (see ``core.evidence.model.classify_confidence_level``) — keeps
    the rescore-after-dismiss path in sync with the CLI's original grade
    so the dashboard, the dim-detail view, and the CLI's JSON report all
    agree on the same number.

    Returns (final_score, grade).
    """
    from quodeq.core.evidence.model import classify_confidence_level  # noqa: PLC0415

    v_dicts = [_finding_to_dict(v) for v in violations]
    c_dicts = [_finding_to_dict(c) for c in compliance]
    vt_counts, ct_counts, _using_taxonomy = compute_tallies(v_dicts, c_dicts)
    if not vt_counts and not ct_counts:
        return None, "Insufficient"

    confidence = classify_confidence_level(
        len(violations), len(compliance),
        scale_multiplier=scale_multiplier,
        source_file_count=source_file_count,
    )
    if confidence == "low":
        return None, "Insufficient"

    base = violation_base(vt_counts, params=params)
    lift = compliance_lift(ct_counts, vt_counts, params=params)
    ceil = violation_ceiling(vt_counts, params=params)
    floor = severity_grade_floor(vt_counts, params=params)

    raw = base + (10.0 - base) * lift
    final = max(floor, min(ceil, raw))
    final = round(final, 1)
    grade = score_to_grade_label(final, params=params)
    return final, grade


def _group_by_principle(
    findings: list[Finding],
) -> dict[str, list[Finding]]:
    """Group a list of findings by their principle name."""
    groups: dict[str, list[Finding]] = {}
    for f in findings:
        groups.setdefault(f.practice_id or "unknown", []).append(f)
    return groups


def _score_all_principles(
    principles_violations: dict[str, list[Finding]],
    principles_compliance: dict[str, list[Finding]],
    *,
    source_file_count: int = 0,
    scale_multiplier: int = 1,
    params: ScoringParams = DEFAULT_PARAMS,
) -> tuple[dict[str, PrincipleScore], list[PrincipleGrade]]:
    """Score each principle and return (scores_dict, grades_list)."""
    all_principle_names = set(principles_violations) | set(principles_compliance)
    principle_scores: dict[str, PrincipleScore] = {}
    principle_grades: list[PrincipleGrade] = []

    for name in sorted(all_principle_names):
        p_violations = principles_violations.get(name, [])
        p_compliance = principles_compliance.get(name, [])
        final_score, grade = _score_principle(
            p_violations, p_compliance,
            source_file_count=source_file_count,
            scale_multiplier=scale_multiplier,
            params=params,
        )
        score_str = f"{final_score}/10" if final_score is not None else None

        principle_scores[name] = PrincipleScore(
            display_name=name, weight="1", final_score=final_score, grade=grade,
        )
        principle_grades.append(PrincipleGrade(principle=name, score=score_str, grade=grade))
    return principle_scores, principle_grades


def _coerce_line(line) -> int:
    """Coerce a Finding.line (typed int|str|None) to the int used in dismiss keys.

    Dismiss keys store line as ``int`` (see services/dismissed.dismissed_keys),
    but a Finding's line may be a string, so a straight ``line or 0`` compare
    would miss a string-lined finding. Coercing here keeps the suppression key
    identical to the stored dismiss key.
    """
    try:
        return int(line)
    except (TypeError, ValueError):
        return 0


def _rescore_dimension(
    dim: DimensionResult,
    dismissed: set[tuple],
    deleted: set[tuple] | None = None,
    params: ScoringParams = DEFAULT_PARAMS,
) -> DimensionResult:
    """Rescore a single dimension after filtering dismissed and deleted findings."""
    deleted = deleted or set()
    dim_id = dim.dimension or ""
    filtered_violations = [
        v for v in dim.violations
        if (v.req or "", v.file or "", _coerce_line(v.line)) not in dismissed
        and (dim_id, v.practice_id or "", v.file or "") not in deleted
    ]
    if len(filtered_violations) == len(dim.violations):
        return dim

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

    compliance_count = dim.totals.compliance_count if dim.totals else len(dim.compliance)
    new_totals = recount_totals(filtered_violations, compliance_count=compliance_count)

    return replace(
        dim,
        violations=filtered_violations,
        principles=principle_grades,
        overall_score=overall_score_str,
        overall_grade=overall_grade,
        totals=new_totals,
    )


def rescore_dimensions(
    dimensions: list[DimensionResult],
    dismissed_keys: set[tuple],
    deleted_keys: set[tuple] | None = None,
    params: ScoringParams | None = None,
) -> dict[str, Any]:
    """Rescore all dimensions after filtering dismissed and deleted findings.

    Returns a dict with 'dimensions' (list of camelCase dicts) and 'summary' (camelCase dict).
    When *params* is None, the saved grade-formula params are loaded.
    """
    if params is None:
        from quodeq.services import grade_formula  # noqa: PLC0415
        params = grade_formula.load_params()
    rescored = [
        _rescore_dimension(dim, dismissed_keys, deleted_keys, params=params)
        for dim in dimensions
    ]
    summary = summarize_dimensions(rescored, params=params)
    return {
        "dimensions": [to_camel_dict(d) for d in rescored],
        "summary": to_camel_dict(summary),
    }
