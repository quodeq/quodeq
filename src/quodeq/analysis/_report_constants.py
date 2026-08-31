"""Shim: report field-name constants moved to ``data/fs/dimension_report``.

The dimension-report cluster is a filesystem I/O adapter, not analysis
logic; it now lives at ``quodeq.data.fs.dimension_report``. This module
re-exports its constants so every pre-existing ``quodeq.analysis._report_constants``
import path keeps working.
"""
from __future__ import annotations

from quodeq.data.fs.dimension_report._report_constants import (  # noqa: F401
    _COMPLIANCE_FIELDS,
    _FIELD_CONFIDENCE_INTERVAL,
    _FIELD_CONFIDENCE_INTERVAL_SNAKE,
    _FIELD_FINAL_SCORE,
    _FIELD_FINAL_SCORE_SNAKE,
    _FIELD_WEIGHTED_SCORE,
    _FIELD_WEIGHTED_SCORE_SNAKE,
    _GRADE_INSUFFICIENT,
    _REPORT_SCHEMA_VERSION,
    _VIOLATION_FIELDS,
)
