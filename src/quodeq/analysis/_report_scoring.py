"""Shim: score-lookup building moved to ``data/fs/dimension_report``; grade
conversion moved to ``core/scoring/report_grades``.

The dimension-report cluster is a filesystem I/O adapter, not analysis
logic; it now lives at ``quodeq.data.fs.dimension_report``. Grade
conversion is pure logic and lives at ``quodeq.core.scoring.report_grades``.
This module re-exports both so every pre-existing
``quodeq.analysis._report_scoring`` import path keeps working.
"""
from __future__ import annotations

from quodeq.core.scoring.report_grades import grade_from_score  # noqa: F401
from quodeq.data.fs.dimension_report.report_scoring import (  # noqa: F401
    build_score_lookup,
    extract_scores,
)
