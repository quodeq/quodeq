"""Re-export for backward compatibility — moved to quodeq.analysis.report."""
from quodeq.analysis.report import (  # noqa: F401
    grade_from_score,
    build_report_json,
    build_full_report,
    build_dashboard_report,
    write_reports,
    write_dimension_report,
    _build_score_lookup,
    _flatten_findings,
    _build_principle_rows,
)
