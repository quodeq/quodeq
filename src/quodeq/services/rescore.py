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
from quodeq.core.types.scoring import PrincipleScore
from quodeq.data.fs.report_parser.grades import summarize_dimensions
from quodeq.services.dismissed import recount_totals


def _finding_to_dict(f: Finding) -> dict[str, Any]:
    """Convert a Finding dataclass to the dict format scoring internals expect.

    The tally functions use 'vt' for violation_type and dict.get() for access.
    """
    return {
        "severity": f.severity or "minor",
        "reason": f.reason or "",
        "vt": f.violation_type or "",
    }


def _score_principle(violations: list[Finding], compliance: list[Finding]) -> tuple[float | None, str]:
    """Score a single principle from its filtered violations and compliance lists.

    Returns (final_score, grade).
    """
    v_dicts = [_finding_to_dict(v) for v in violations]
    c_dicts = [_finding_to_dict(c) for c in compliance]
    vt_counts, ct_counts, _using_taxonomy = compute_tallies(v_dicts, c_dicts)
    if not vt_counts and not ct_counts:
        return None, "Insufficient"

    base = violation_base(vt_counts)
    lift = compliance_lift(ct_counts, vt_counts)
    ceil = violation_ceiling(vt_counts)
    floor = severity_grade_floor(vt_counts)

    raw = base + (10.0 - base) * lift
    final = max(floor, min(ceil, raw))
    final = round(final, 1)
    grade = score_to_grade_label(final)
    return final, grade


def _rescore_dimension(dim: DimensionResult, dismissed: set[tuple]) -> DimensionResult:
    """Rescore a single dimension after filtering dismissed findings."""
    # Filter violations -- dismissed key is (req, file, line)
    filtered_violations = [
        v for v in dim.violations
        if (v.req or "", v.file or "", v.line or 0) not in dismissed
    ]

    # Group violations and compliance by principle
    principles_violations: dict[str, list[Finding]] = {}
    principles_compliance: dict[str, list[Finding]] = {}
    for v in filtered_violations:
        principles_violations.setdefault(v.principle or "unknown", []).append(v)
    for c in dim.compliance:
        principles_compliance.setdefault(c.principle or "unknown", []).append(c)

    # Score each principle
    all_principle_names = set(principles_violations) | set(principles_compliance)
    principle_scores: dict[str, PrincipleScore] = {}
    principle_grades: list[PrincipleGrade] = []

    for name in sorted(all_principle_names):
        p_violations = principles_violations.get(name, [])
        p_compliance = principles_compliance.get(name, [])
        final_score, grade = _score_principle(p_violations, p_compliance)
        score_str = f"{final_score}/10" if final_score is not None else None

        principle_scores[name] = PrincipleScore(
            display_name=name,
            weight="1",
            final_score=final_score,
            grade=grade,
        )
        principle_grades.append(PrincipleGrade(principle=name, score=score_str, grade=grade))

    # Aggregate to dimension overall
    overall = weighted_overall(principle_scores, MODE_NUMERICAL)
    overall_score_str = f"{overall.weighted_score}/10" if overall.weighted_score is not None else None
    overall_grade = overall.grade or overall.weighted_grade

    # Recount totals
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
) -> dict[str, Any]:
    """Rescore all dimensions after filtering dismissed findings.

    Returns a dict with 'dimensions' (list of camelCase dicts) and 'summary' (camelCase dict).
    """
    rescored = [_rescore_dimension(dim, dismissed_keys) for dim in dimensions]
    summary = summarize_dimensions(rescored)
    return {
        "dimensions": [to_camel_dict(d) for d in rescored],
        "summary": to_camel_dict(summary),
    }
