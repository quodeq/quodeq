"""Shim: report assembly moved to ``data/fs/dimension_report``.

The dimension-report cluster is a filesystem I/O adapter, not analysis
logic; it now lives at ``quodeq.data.fs.dimension_report``. This module
re-exports its names so every pre-existing ``quodeq.analysis._report_assembly``
import path keeps working.
"""
from __future__ import annotations

from quodeq.data.fs.dimension_report._report_assembly import (  # noqa: F401
    _ReportData,
    _assemble_report_dict,
    build_dashboard_report,
    build_full_report,
    build_report_json,
)
