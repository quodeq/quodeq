"""Grade calculation, scoring, and dimension summary helpers.

This module re-exports from focused sub-modules for backward compatibility.
"""

from quodeq.data.fs.report_parser._scoring import (
    NUMERIC_GRADE_ORDER,
    TEXT_GRADE_ORDER,
    calculate_trend,
    most_frequent_grade,
    parse_numeric_score,
)
from quodeq.data.fs.report_parser._summary import summarize_dimensions
from quodeq.data.fs.report_parser._totals import SEVERITIES, build_totals

__all__ = [
    "NUMERIC_GRADE_ORDER",
    "SEVERITIES",
    "TEXT_GRADE_ORDER",
    "build_totals",
    "calculate_trend",
    "most_frequent_grade",
    "parse_numeric_score",
    "summarize_dimensions",
]
