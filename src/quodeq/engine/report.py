"""Re-export for backward compatibility — moved to quodeq.analysis.report."""
from quodeq.analysis.report import *  # noqa: F401,F403
from quodeq.analysis.report import (  # noqa: F401
    build_dashboard_report,
    build_full_report,
    build_report_json,
    grade_from_score,
    write_dimension_report,
    write_reports,
    _build_principle_rows,
    _build_score_lookup,
    _flatten_findings,
)
