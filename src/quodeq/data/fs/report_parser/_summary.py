"""Dimension summary aggregation across multiple evaluation results."""

from __future__ import annotations

from quodeq.core.types import DimensionResult, DimensionSummary
from quodeq.core.scoring.dimension_summary import build_dimension_summary
from quodeq.core.scoring.internals import score_to_grade_label
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams, dimension_weighted_average
from quodeq.data.fs.report_parser._scoring import most_frequent_grade, parse_numeric_score


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
    # falling back to most-frequent vote when scores are absent.
    if numeric_average is not None:
        overall_grade = score_to_grade_label(numeric_average, params=params)
    else:
        overall_grade = most_frequent_grade(overall_grades)

    return build_dimension_summary(
        len(dimensions), overall_grades, overall_grade, numeric_average,
    )
