"""Shim: score/grade conversion moved to ``data/fs/dimension_report``.

The dimension-report cluster is a filesystem I/O adapter, not analysis
logic; it now lives at ``quodeq.data.fs.dimension_report``. This module
re-exports its public names so every pre-existing
``quodeq.analysis._report_scoring`` import path keeps working.
"""
from __future__ import annotations

from quodeq.data.fs.dimension_report._report_scoring import (  # noqa: F401
    build_score_lookup,
    extract_scores,
    grade_from_score,
)
