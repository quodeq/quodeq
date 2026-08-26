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


def test_commits_since_counts_against_a_real_repo(tmp_path):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": __import__("os").environ["PATH"]}

    def git(*args, date=None):
        e = dict(env)
        if date:
            e["GIT_AUTHOR_DATE"] = date
            e["GIT_COMMITTER_DATE"] = date
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=e)

    git("init", "-q")
    (repo / "a.txt").write_text("one")
    git("add", ".")
    git("commit", "-qm", "one", date="2026-08-01T10:00:00")
    (repo / "a.txt").write_text("two")
    git("commit", "-aqm", "two", date="2026-08-20T10:00:00")

    assert compare._commits_since(repo, "2026-08-10T00:00:00") == 1
    assert compare._commits_since(repo, "2026-07-01T00:00:00") == 2
    # Fails open on anything unknowable.
    assert compare._commits_since(None, "2026-08-10T00:00:00") is None
    assert compare._commits_since(repo, None) is None
    assert compare._commits_since(tmp_path / "not-a-repo", "2026-08-10T00:00:00") is None


def test_summary_carries_commits_since_last_scored_run(monkeypatch, scores_stub):
    seen = {}

    def fake_commits(repo_root, since_iso):
        seen["since"] = since_iso
        return 7

    monkeypatch.setattr(compare, "_local_repo_root", lambda root, project: Path("/tmp/repo"))
    monkeypatch.setattr(compare, "_commits_since", fake_commits)
    result = compare.build_compare_summary(Path("/tmp/evals"), "proj-a")
    assert result["commitsSinceLastRun"] == 7
    # Counted from the newest scored run's date, not the raw last run.
    assert seen["since"] == "2026-08-01T10:00:00"


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
