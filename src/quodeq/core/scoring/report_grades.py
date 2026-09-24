"""Pure score-string parsing, grade ranking, trend and dimension roll-up."""

from __future__ import annotations

import re
from typing import Any

from quodeq.core.scoring.constants import Grade
from quodeq.core.scoring.internals import GRADE_LADDER, score_to_grade_label
from quodeq.core.scoring.dimension_summary import build_dimension_summary
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams, dimension_weighted_average
from quodeq.core.types import DimensionResult, DimensionSummary

# "Critical" is the lowest label older numeric reports wrote; it has no Grade member.
NUMERIC_GRADE_ORDER = ["Critical", Grade.POOR, Grade.ADEQUATE, Grade.GOOD, Grade.EXEMPLARY]
TEXT_GRADE_ORDER = GRADE_LADDER

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


def summarize_dimensions(
    dimensions: list[DimensionResult],
    params: ScoringParams = DEFAULT_PARAMS,
) -> DimensionSummary:
    """Produce an aggregate summary across multiple dimension evaluation results.

    Example::

        summarize_dimensions([DimensionResult(dimension="security", overall_grade="Good", overall_score="8/10")])
    """
    overall_grades = [d.overall_grade for d in dimensions if d.overall_grade]
    score_pairs = [
        (d.dimension, score)
        for d, score in (
            (d, parse_numeric_score(d.overall_score)) for d in dimensions
        )
        if score is not None
    ]
    numeric_average = dimension_weighted_average(score_pairs, params)

    # Derive overall grade from the numeric average when available,
    # falling back to most-frequent vote when scores are absent. This path
    # breaks a vote tie on grade rank (most_frequent_grade); the services
    # path breaks it on Counter insertion order. Deliberate: only this one
    # has the rank table, and the two feed different responses.
    if numeric_average is not None:
        overall_grade = score_to_grade_label(numeric_average, params=params)
    else:
        overall_grade = most_frequent_grade(overall_grades)

    return build_dimension_summary(
        len(dimensions), overall_grades, overall_grade, numeric_average,
    )


def grade_from_score(score: str | None) -> str | None:
    """Convert a numeric score string (e.g. '7/10') to a grade label.

    Anchored at the start (``re.match``), unlike :func:`parse_numeric_score`.
    """
    if not score:
        return None
    hit = _SCORE_RE.match(str(score))
    if not hit:
        return None
    return score_to_grade_label(float(hit.group(1)))
