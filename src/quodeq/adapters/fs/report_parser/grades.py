"""Re-export shim — canonical location is quodeq.data.fs.report_parser.grades."""
from quodeq.data.fs.report_parser.grades import (
    NUMERIC_GRADE_ORDER,
    SEVERITIES,
    TEXT_GRADE_ORDER,
    build_totals,
    calculate_trend,
    most_frequent_grade,
    parse_numeric_score,
    summarize_dimensions,
)

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
