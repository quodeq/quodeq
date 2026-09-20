"""Shim: findings flattening/principle-row building moved to ``data/fs/dimension_report``.

The dimension-report cluster is a filesystem I/O adapter, not analysis
logic; it now lives at ``quodeq.data.fs.dimension_report``. This module
re-exports its names so every pre-existing ``quodeq.analysis._report_findings``
import path keeps working.
"""
from __future__ import annotations

from quodeq.data.fs.dimension_report.report_findings import (  # noqa: F401
    build_principle_row,
    flatten_findings,
    build_principle_rows,
)
