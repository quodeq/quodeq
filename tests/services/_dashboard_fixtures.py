"""Shared builders for tests/services/test_dashboard_*.py siblings.

Split out of test_dashboard.py (quodeq.services.dashboard — dashboard
construction logic).
"""
from __future__ import annotations

from quodeq.core.types import DimensionResult
from quodeq.data.fs.report_parser import RunInfo


def _make_run(run_id: str, date_iso: str = "2024-01-01") -> RunInfo:
    return RunInfo(run_id=run_id, date_iso=date_iso, date_label=date_iso)


def _dim(name: str, grade: str = "B", score: str = "7.0") -> DimensionResult:
    return DimensionResult(dimension=name, overall_grade=grade, overall_score=score)
