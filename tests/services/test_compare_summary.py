"""Tests for services.compare.build_compare_summary (Compare tab payload).

The contract under test: the slim payload is the full /scores payload minus
the finding arrays -- scores, grades, principles, totals and trend all pass
through untouched, and the heavy keys are gone at every level.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.services import compare


_SCORES_PAYLOAD = {
    "accumulated": {
        "dimensions": [
            {
                "dimension": "Security",
                "overallScore": "7.0/10",
                "overallGrade": "Good",
                "principles": [{"principle": "Integrity", "score": "7.0", "grade": "Good"}],
                "totals": {
                    "violationCount": 3,
                    "complianceCount": 9,
                    "severity": {"critical": 1, "major": 1, "minor": 1},
                },
                "filesRead": 40,
                "sourceFileCount": 50,
                "violations": [{"file": "a.py", "line": 10, "reason": "weak hash"}],
                "compliance": [{"file": "b.py", "line": 2, "reason": "ok"}],
            },
        ],
        "summary": {
            "overallGrade": "Good",
            "numericAverage": 7.0,
            "totalViolations": 3,
            "totalCompliance": 9,
            "severity": {"critical": 1, "major": 1, "minor": 1},
        },
    },
    "trend": [
        {
            "runId": "run-1",
            "dateISO": "2026-08-01T10:00:00",
            "dateLabel": "01 Aug",
            "status": "complete",
            "numericAverage": 7.0,
            "overallGrade": "Good",
            "runNumericAverage": 7.0,
            "dimensionDetails": [
                {"dimension": "Security", "score": 7.0, "grade": "Good", "delta": 0.2},
            ],
        },
    ],
    "availableRuns": [
        {"runId": "run-1", "dateLabel": "01 Aug", "status": "complete"},
    ],
    "scoring": {"customFormula": False},
}


@pytest.fixture()
def scores_stub(monkeypatch):
    calls = []

    def fake_get_project_scores(reports_root, project):
        calls.append((reports_root, project))
        return _SCORES_PAYLOAD

    monkeypatch.setattr(compare, "get_project_scores", fake_get_project_scores)
    return calls


def test_strips_finding_arrays_from_dimensions(scores_stub):
    result = compare.build_compare_summary(Path("/tmp/evals"), "proj-a")
    dim = result["dimensions"][0]
    assert "violations" not in dim
    assert "compliance" not in dim
    # Everything light passes through untouched.
    assert dim["overallScore"] == "7.0/10"
    assert dim["principles"] == [{"principle": "Integrity", "score": "7.0", "grade": "Good"}]
    assert dim["totals"]["severity"] == {"critical": 1, "major": 1, "minor": 1}


def test_summary_and_scoring_pass_through(scores_stub):
    result = compare.build_compare_summary(Path("/tmp/evals"), "proj-a")
    assert result["project"] == "proj-a"
    assert result["summary"]["numericAverage"] == 7.0
    assert result["scoring"] == {"customFormula": False}
    assert result["runsCount"] == 1
    assert result["lastRun"]["runId"] == "run-1"


def test_trend_detail_keeps_only_dimension_and_score(scores_stub):
    result = compare.build_compare_summary(Path("/tmp/evals"), "proj-a")
    entry = result["trend"][0]
    assert entry["numericAverage"] == 7.0
    assert entry["dimensionDetails"] == [{"dimension": "Security", "score": 7.0}]


def test_unknown_project_returns_none(monkeypatch):
    monkeypatch.setattr(compare, "get_project_scores", lambda *a, **kw: None)
    assert compare.build_compare_summary(Path("/tmp/evals"), "ghost") is None


def test_no_runs_shape(monkeypatch):
    monkeypatch.setattr(
        compare, "get_project_scores",
        lambda *a, **kw: {
            "accumulated": {"dimensions": [], "summary": {}},
            "trend": [],
            "availableRuns": [],
            "scoring": {"customFormula": False},
        },
    )
    result = compare.build_compare_summary(Path("/tmp/evals"), "empty")
    assert result["dimensions"] == []
    assert result["trend"] == []
    assert result["runsCount"] == 0
    assert result["lastRun"] is None
