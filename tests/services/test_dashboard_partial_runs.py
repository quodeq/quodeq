"""``partialRuns`` on the dashboard payload: cancelled runs with their own scores.

A cancelled run is not a history point (it stays out of ``trend``, so the
chart and every accumulated number are unchanged), but it is a real
evaluation the user kept. History lists it with the run's own grade.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from quodeq.core.run.state import RunState
from quodeq.core.types import DimensionSummary
from quodeq.data.fs.report_parser import RunInfo
from quodeq.services.dashboard import build_dashboard
from tests.services._dashboard_fixtures import _dim

DONE = RunInfo(run_id="r-done", date_iso="2024-03-01", date_label="2024-03-01", status=RunState.DONE)
SCORED = RunInfo(run_id="r-scored", date_iso="2024-02-01", date_label="2024-02-01", status=RunState.CANCELLED)
EMPTY = RunInfo(run_id="r-empty", date_iso="2024-01-15", date_label="2024-01-15", status=RunState.CANCELLED)
FAILED = RunInfo(run_id="r-failed", date_iso="2024-01-01", date_label="2024-01-01", status=RunState.FAILED)

DIMS = {
    "r-done": [_dim("security", "B", "7.0"), _dim("usability", "A", "9.0")],
    "r-scored": [_dim("security", "C", "5.0")],
    "r-empty": [],
    "r-failed": [_dim("security", "A", "9.5")],
}


def _read(_root, _project, run_id):
    if run_id not in DIMS:
        raise FileNotFoundError(f"Run not found: proj/{run_id}")
    return DIMS[run_id]


@pytest.fixture()
def dashboard(tmp_path):
    summary = DimensionSummary(dimensions_count=2, overall_grade="B", numeric_average=8.0)
    with (
        patch("quodeq.services.dashboard.list_runs", return_value=[DONE, SCORED, EMPTY, FAILED]),
        patch("quodeq.services.dashboard.read_run_data", side_effect=_read),
        patch("quodeq.data.fs.report_parser.runs.read_run_data", side_effect=_read),
        patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
    ):
        yield build_dashboard(str(tmp_path), "proj", "latest")


def test_cancelled_run_with_scored_dims_is_listed_with_its_own_scores(dashboard):
    (entry,) = dashboard["partialRuns"]

    assert entry["runId"] == "r-scored"
    assert entry["status"] is RunState.CANCELLED
    assert entry["dateISO"] == "2024-02-01"
    assert entry["runNumericAverage"] == pytest.approx(5.0)
    assert entry["runOverallGrade"]
    assert entry["dimensions"] == ["security"]
    assert entry["dimensionsCount"] == 1
    assert entry["dimensionDetails"] == [
        {"dimension": "security", "score": 5.0, "grade": "C", "delta": None},
    ]


def test_partial_run_carries_no_accumulated_score(dashboard):
    """The accumulated fields drive the History deltas and the Overview; a
    cancelled run must not feed either."""
    (entry,) = dashboard["partialRuns"]

    assert entry["numericAverage"] is None
    assert entry["overallGrade"] is None
    assert entry["accumulatedDimensionsCount"] == 0


def test_cancelled_run_with_nothing_scored_is_left_out(dashboard):
    assert [e["runId"] for e in dashboard["partialRuns"]] == ["r-scored"]


def test_failed_run_is_never_a_partial_run(dashboard):
    assert "r-failed" not in [e["runId"] for e in dashboard["partialRuns"]]


def test_trend_is_unchanged(dashboard):
    assert [e["runId"] for e in dashboard["trend"]] == ["r-done"]


def test_unreadable_cancelled_run_does_not_break_the_dashboard(tmp_path):
    gone = RunInfo(run_id="r-gone", date_iso="2024-02-15", date_label="2024-02-15", status=RunState.CANCELLED)
    summary = DimensionSummary(dimensions_count=2, overall_grade="B", numeric_average=8.0)
    with (
        patch("quodeq.services.dashboard.list_runs", return_value=[DONE, gone, SCORED]),
        patch("quodeq.services.dashboard.read_run_data", side_effect=_read),
        patch("quodeq.data.fs.report_parser.runs.read_run_data", side_effect=_read),
        patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
    ):
        result = build_dashboard(str(tmp_path), "proj", "latest")

    assert [e["runId"] for e in result["partialRuns"]] == ["r-scored"]


def test_all_cancelled_project_lists_its_scored_runs(tmp_path):
    summary = DimensionSummary(dimensions_count=1, overall_grade="C", numeric_average=5.0)
    with (
        patch("quodeq.services.dashboard.list_runs", return_value=[SCORED, EMPTY]),
        patch("quodeq.services.dashboard.read_run_data", side_effect=_read),
        patch("quodeq.data.fs.report_parser.runs.read_run_data", side_effect=_read),
        patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
    ):
        result = build_dashboard(str(tmp_path), "proj", "latest")

    assert [e["runId"] for e in result["partialRuns"]] == ["r-scored"]
    assert result["trend"] == []
