"""Grade calculation, scoring, and dimension summary helpers."""

from __future__ import annotations

import logging
import re
from typing import Any

from quodeq.core.types import DimensionResult, DimensionSummary, Finding, GradeBreakdown, SeverityTally, Totals
from quodeq.engine.scoring_internals import GRADE_LADDER, score_to_grade_label

_logger = logging.getLogger(__name__)

NUMERIC_GRADE_ORDER = ["Critical", "Poor", "Adequate", "Good", "Exemplary"]
TEXT_GRADE_ORDER = GRADE_LADDER
SEVERITIES = {"critical", "major", "minor", "unknown"}
_SCORE_DECIMAL_PLACES = 1

_SCORE_RE = re.compile(r"(\d+(?:\.\d+)?)")
_NUMERIC_RANK: dict[str, int] = {g: i for i, g in enumerate(NUMERIC_GRADE_ORDER)}
_TEXT_RANK: dict[str, int] = {g: i for i, g in enumerate(TEXT_GRADE_ORDER)}


def parse_numeric_score(score_text: str | None) -> float | None:
    """Extract the first numeric value from a score string, or return None.

    Example::

        parse_numeric_score("7.5/10")  # -> 7.5
        parse_numeric_score("no score")  # -> None
    """
    if not score_text:
        return None
    match = _SCORE_RE.search(str(score_text))
    if not match:
        _logger.debug("No numeric score found in %r; expected format like '7.5/10'", score_text)
        return None
    return float(match.group(1))


def _grade_rank(grade: str) -> int:
    """Return the ordinal rank of a grade (higher is better), or -1 if unknown."""
    rank = _NUMERIC_RANK.get(grade)
    if rank is not None:
        return rank
    return _TEXT_RANK.get(grade, -1)


def most_frequent_grade(grades: list[str]) -> str | None:
    """Return the most common grade, breaking ties by higher grade rank.

    Example::

        most_frequent_grade(["Good", "Good", "Poor"])  # -> "Good"
    """
    if not grades:
        return None
    counts: dict[str, int] = {}
    for grade in grades:
        counts[grade] = counts.get(grade, 0) + 1
    # Sort by (-count, -rank) so the highest-count, highest-rank grade wins.
    return max(counts, key=lambda g: (counts[g], _grade_rank(g)))


def build_totals(violations: list[Finding], compliance: list[Finding]) -> Totals:
    """Aggregate violation and compliance counts grouped by severity.

    Example::

        build_totals([Finding(severity="major")], [Finding(severity="minor")])
    """
    severity: dict[str, int] = {k: 0 for k in SEVERITIES}
    for entry in violations:
        key = entry.severity or "unknown"
        if key not in SEVERITIES:
            key = "unknown"
        severity[key] += 1
    return Totals(
        violation_count=len(violations),
        compliance_count=len(compliance),
        severity=SeverityTally(
            critical=severity["critical"],
            major=severity["major"],
            minor=severity["minor"],
            unknown=severity["unknown"],
        ),
    )


def calculate_trend(current_score: Any, previous_score: Any) -> str:
    """Compare two scores and return a trend direction: 'up', 'down', 'same', or 'none'.

    Example::

        calculate_trend("8/10", "6/10")  # -> "up"
    """
    current = parse_numeric_score(str(current_score)) if current_score is not None else None
    previous = parse_numeric_score(str(previous_score)) if previous_score is not None else None
    if current is None or previous is None:
        return "none"
    if current > previous:
        return "up"
    if current < previous:
        return "down"
    return "same"


def summarize_dimensions(dimensions: list[DimensionResult]) -> DimensionSummary:
    """Produce an aggregate summary across multiple dimension evaluation results.

    Example::

        summarize_dimensions([DimensionResult(dimension="security", overall_grade="Good", overall_score="8/10")])
    """
    overall_grades = [d.overall_grade for d in dimensions if d.overall_grade]
    numeric_scores = [
        score for score in (parse_numeric_score(d.overall_score) for d in dimensions) if score is not None
    ]
    numeric_average = None
    if numeric_scores:
        numeric_average = round(sum(numeric_scores) / len(numeric_scores), _SCORE_DECIMAL_PLACES)

    grade_counts: dict[str, int] = {}
    for grade in overall_grades:
        grade_counts[grade] = grade_counts.get(grade, 0) + 1

    # Derive overall grade from the numeric average when available,
    # falling back to most-frequent vote when scores are absent.
    if numeric_average is not None:
        overall_grade = score_to_grade_label(numeric_average)
    else:
        overall_grade = most_frequent_grade(overall_grades)

    return DimensionSummary(
        dimensions_count=len(dimensions),
        overall_grade=overall_grade,
        numeric_average=numeric_average,
        grade_breakdown=[
            GradeBreakdown(grade=grade, count=count)
            for grade, count in sorted(grade_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    )
