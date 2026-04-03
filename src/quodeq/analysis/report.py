"""Report builder -- public API re-exported from focused sub-modules.

Sub-modules:
  _report_constants  -- field-name constants
  _report_scoring    -- score/grade conversion and lookup building
  _report_findings   -- findings flattening and principle-row building
  _report_assembly   -- report dict assembly
  _report_io         -- disk persistence (I/O adapters)
"""
from __future__ import annotations

from quodeq.analysis._report_scoring import grade_from_score
from quodeq.analysis._report_assembly import (
    build_report_json,
    build_full_report,
    build_dashboard_report,
)
from quodeq.analysis._report_io import (
    write_reports,
    write_dimension_report,
)

__all__ = [
    "grade_from_score",
    "build_report_json",
    "build_full_report",
    "build_dashboard_report",
    "write_reports",
    "write_dimension_report",
]
