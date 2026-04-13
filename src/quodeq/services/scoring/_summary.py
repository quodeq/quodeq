"""Recompute accumulated summary from rescored dimension dicts."""
from __future__ import annotations

from typing import Any

from quodeq.core.scoring.internals import score_to_grade_label
from quodeq.services.ports import most_frequent_grade, parse_numeric_score


def recompute_summary(
    dimensions: list[dict[str, Any]],
    old_summary: dict[str, Any],
) -> dict[str, Any]:
    """Recompute the accumulated summary from rescored camelCase dimension dicts."""
    scores: list[float] = []
    grades: list[str] = []
    total_violations = 0
    total_compliance = 0
    critical = major = minor = 0

    for d in dimensions:
        score_str = d.get("overallScore")
        if score_str:
            val = parse_numeric_score(score_str)
            if val is not None:
                scores.append(val)
        grade = d.get("overallGrade")
        if grade:
            grades.append(grade)
        totals = d.get("totals") or {}
        total_violations += totals.get("violationCount", 0)
        total_compliance += totals.get("complianceCount", 0)
        severity = totals.get("severity") or {}
        critical += severity.get("critical", 0)
        major += severity.get("major", 0)
        minor += severity.get("minor", 0)

    avg = round(sum(scores) / len(scores), 1) if scores else None
    overall_grade = (
        score_to_grade_label(avg) if avg is not None
        else (most_frequent_grade(grades) if grades else None)
    )

    return {
        **old_summary,
        "overallGrade": overall_grade,
        "numericAverage": avg,
        "totalViolations": total_violations,
        "totalCompliance": total_compliance,
        "dimensionCount": len(dimensions),
        "severity": {
            "critical": critical,
            "major": major,
            "minor": minor,
        },
    }
