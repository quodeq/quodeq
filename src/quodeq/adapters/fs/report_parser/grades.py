"""Grade calculation, scoring, and dimension summary helpers."""

from __future__ import annotations

import re
from typing import Any


NUMERIC_GRADE_ORDER = ["Critical", "Poor", "Adequate", "Good", "Exemplary"]
TEXT_GRADE_ORDER = ["Insufficient", "Developing", "Proficient", "Exemplary"]
SEVERITIES = {"critical", "major", "minor", "unknown"}


def parse_numeric_score(score_text: str | None) -> float | None:
    """Extract the first numeric value from a score string, or return None."""
    if not score_text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", str(score_text))
    if not match:
        return None
    return float(match.group(1))


def most_frequent_grade(grades: list[str]) -> str | None:
    """Return the most common grade, breaking ties by higher grade rank."""
    if not grades:
        return None
    counts: dict[str, int] = {}
    for grade in grades:
        counts[grade] = counts.get(grade, 0) + 1
    winner = grades[0]
    winner_count = counts[winner]
    for grade, count in counts.items():
        if count > winner_count:
            winner = grade
            winner_count = count
            continue
        if count == winner_count:
            if grade in NUMERIC_GRADE_ORDER and winner in NUMERIC_GRADE_ORDER:
                if NUMERIC_GRADE_ORDER.index(grade) > NUMERIC_GRADE_ORDER.index(winner):
                    winner = grade
                    continue
            if grade in TEXT_GRADE_ORDER and winner in TEXT_GRADE_ORDER:
                if TEXT_GRADE_ORDER.index(grade) > TEXT_GRADE_ORDER.index(winner):
                    winner = grade
    return winner


def build_totals(violations: list[dict[str, Any]], compliance: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate violation and compliance counts grouped by severity."""
    severity = {"critical": 0, "major": 0, "minor": 0, "unknown": 0}
    for entry in violations:
        key = entry.get("severity", "unknown")
        if key not in SEVERITIES:
            key = "unknown"
        severity[key] += 1
    return {
        "violationCount": len(violations),
        "complianceCount": len(compliance),
        "severity": severity,
    }


def calculate_trend(current_score: Any, previous_score: Any) -> str:
    """Compare two scores and return a trend direction: 'up', 'down', 'same', or 'none'."""
    current = parse_numeric_score(str(current_score)) if current_score is not None else None
    previous = parse_numeric_score(str(previous_score)) if previous_score is not None else None
    if current is None or previous is None:
        return "none"
    if current > previous:
        return "up"
    if current < previous:
        return "down"
    return "same"


def summarize_dimensions(dimensions: list[dict[str, Any]]) -> dict[str, Any]:
    """Produce an aggregate summary across multiple dimension evaluation results."""
    overall_grades = [d.get("overallGrade") for d in dimensions if d.get("overallGrade")]
    numeric_scores = [
        score for score in (parse_numeric_score(d.get("overallScore")) for d in dimensions) if score is not None
    ]
    numeric_average = None
    if numeric_scores:
        numeric_average = round(sum(numeric_scores) / len(numeric_scores), 1)

    grade_breakdown: dict[str, int] = {}
    for grade in overall_grades:
        grade_breakdown[grade] = grade_breakdown.get(grade, 0) + 1

    return {
        "dimensionsCount": len(dimensions),
        "overallGrade": most_frequent_grade(overall_grades),
        "numericAverage": numeric_average,
        "gradeBreakdown": [
            {"grade": grade, "count": count}
            for grade, count in sorted(grade_breakdown.items(), key=lambda item: (-item[1], item[0]))
        ],
    }
