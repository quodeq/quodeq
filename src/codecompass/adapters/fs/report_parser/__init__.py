"""Report parser package — split into sub-modules by responsibility."""
from codecompass.adapters.fs.report_parser.grades import (
    NUMERIC_GRADE_ORDER,
    SEVERITIES,
    TEXT_GRADE_ORDER,
    build_totals,
    calculate_trend,
    most_frequent_grade,
    parse_numeric_score,
    summarize_dimensions,
)
from codecompass.adapters.fs.report_parser.json_parser import (
    parse_eval_from_json,
    parse_evidence_file,
    parse_report_json,
)
from codecompass.adapters.fs.report_parser.markdown import (
    clean_cell,
    extract_exec_summary,
    is_divider_row,
    parse_eval_markdown,
    split_table_row,
)
from codecompass.adapters.fs.report_parser.runs import (
    RunInfo,
    _get_previous_run_for_dimension,
    _normalize_date,
    _parse_run_date,
    build_repository_info,
    list_runs,
    read_run_data,
    safe_read_dir,
)

__all__ = [
    "NUMERIC_GRADE_ORDER",
    "SEVERITIES",
    "TEXT_GRADE_ORDER",
    "RunInfo",
    "build_repository_info",
    "build_totals",
    "calculate_trend",
    "clean_cell",
    "extract_exec_summary",
    "is_divider_row",
    "list_runs",
    "most_frequent_grade",
    "parse_eval_from_json",
    "parse_eval_markdown",
    "parse_evidence_file",
    "parse_numeric_score",
    "parse_report_json",
    "read_run_data",
    "safe_read_dir",
    "split_table_row",
    "summarize_dimensions",
]
