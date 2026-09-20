"""Shim: report field-name constants moved to ``data/fs/dimension_report``.

The dimension-report cluster is a filesystem I/O adapter, not analysis
logic; it now lives at ``quodeq.data.fs.dimension_report``. This module
re-exports its constants so every pre-existing ``quodeq.analysis._report_constants``
import path keeps working.
"""
from __future__ import annotations

from quodeq.data.fs.dimension_report.report_constants import (  # noqa: F401
    COMPLIANCE_FIELDS,
    FIELD_CONFIDENCE_INTERVAL,
    FIELD_CONFIDENCE_INTERVAL_SNAKE,
    FIELD_FINAL_SCORE,
    FIELD_FINAL_SCORE_SNAKE,
    FIELD_WEIGHTED_SCORE,
    FIELD_WEIGHTED_SCORE_SNAKE,
    GRADE_INSUFFICIENT,
    REPORT_SCHEMA_VERSION,
    VIOLATION_FIELDS,
)
