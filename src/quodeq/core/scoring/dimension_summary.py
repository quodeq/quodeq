"""The one way a :class:`DimensionSummary` and its grade breakdown are built.

Two callers aggregate dimensions into a summary -- the report parser
(``data.fs.report_parser``) and the scores response builder
(``services.scoring``). Both need the same breakdown ordering, so the
construction lives here instead of in each.

What is deliberately NOT shared is how each caller picks *overall_grade*
when there is no numeric average to derive it from: the parser breaks a
tied vote on grade rank, the services builder on ``Counter`` insertion
order. Only the parser side has the rank table, so the tie-break stays
with each caller and this function takes the already-chosen grade.
"""
from __future__ import annotations

from collections.abc import Iterable

from quodeq.core.types import DimensionSummary, GradeBreakdown


def build_dimension_summary(
    dimensions_count: int,
    overall_grades: Iterable[str],
    overall_grade: str | None,
    numeric_average: float | None,
) -> DimensionSummary:
    """A summary whose breakdown tallies *overall_grades*, commonest first.

    Ties break on the grade label, so the breakdown order is deterministic
    for a given set of grades.
    """
    grade_counts: dict[str, int] = {}
    for grade in overall_grades:
        grade_counts[grade] = grade_counts.get(grade, 0) + 1
    return DimensionSummary(
        dimensions_count=dimensions_count,
        overall_grade=overall_grade,
        numeric_average=numeric_average,
        grade_breakdown=[
            GradeBreakdown(grade=grade, count=count)
            for grade, count in sorted(grade_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    )
