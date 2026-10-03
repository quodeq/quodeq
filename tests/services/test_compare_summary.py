"""Tests for services.compare.build_compare_summary (Compare tab payload).

The contract under test: the slim payload is the /scores shape minus the
finding arrays, built from the project's rows (``ProjectRows``) for a plain
project and from ``get_project_scores`` for a parent; the fleet build isolates
each project's failure and runs under one score-cache session.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from quodeq.core.run.state import RunState
from quodeq.data.fs.report_parser import RunInfo
from quodeq.services import compare


_DIMENSION = {
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
    "evidenceDate": "2026-08-01T10:00:00",
    "violations": [],
    "compliance": [],
}
_ACCUMULATED = {
    "dimensions": [_DIMENSION],
    "summary": {
        "overallGrade": "Good",
        "numericAverage": 7.0,
        "totalViolations": 3,
        "totalCompliance": 9,
        "severity": {"critical": 1, "major": 1, "minor": 1},
    },
}
_TREND = [
    {
        "runId": "run-1",
        "dateISO": "2026-08-01T10:00:00",
        "dateLabel": "01 Aug",
        "status": "done",
        "numericAverage": 7.0,
        "overallGrade": "Good",
        "runNumericAverage": 7.0,
        "dimensionDetails": [
            {"dimension": "Security", "score": 7.0, "grade": "Good", "delta": 0.2},
        ],
    },
]
RUN = RunInfo(run_id="run-1", date_iso="2026-08-01T10:00:00", date_label="01 Aug", status=RunState.DONE)


class _Rows:
    """A ``ProjectRows`` double: canned accumulated + trend, records what was asked."""

    loaded: list[tuple[Path, str]] = []

    def __init__(self, runs: list[RunInfo]) -> None:
        self.runs = runs
        self.as_of_calls: list[str | None] = []

    @classmethod
    def load(cls, reports_root: Path, project: str, deps=None) -> "_Rows":
        cls.loaded.append((reports_root, project))
        return cls(cls.runs_for(project))

    @staticmethod
    def runs_for(project: str) -> list[RunInfo]:
        return [] if project == "empty" else [RUN]

    def accumulated(self, as_of: str | None = None) -> dict:
        self.as_of_calls.append(as_of)
        return _ACCUMULATED

    def trend(self) -> list[dict]:
        return _TREND


@pytest.fixture()
def rows_stub(monkeypatch, tmp_path):
    """A non-parent project served from rows; ``get_project_scores`` must stay untouched."""
    _Rows.loaded = []
    for name in ("proj-a", "empty"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(compare, "ProjectRows", _Rows)
    monkeypatch.setattr(compare, "find_children", lambda root, project: [])
    monkeypatch.setattr(compare, "is_custom", lambda: False)
    monkeypatch.setattr(compare, "get_project_scores", _fail_full_path)
    return tmp_path


def _fail_full_path(*a, **kw):
    raise AssertionError("a non-parent project must not take the full get_project_scores path")


def test_strips_finding_arrays_from_dimensions(rows_stub):
    result = compare.build_compare_summary(rows_stub, "proj-a")
    dim = result["dimensions"][0]
    assert "violations" not in dim
    assert "compliance" not in dim
    # Everything light passes through untouched.
    assert dim["overallScore"] == "7.0/10"
    assert dim["principles"] == [{"principle": "Integrity", "score": "7.0", "grade": "Good"}]
    assert dim["totals"]["severity"] == {"critical": 1, "major": 1, "minor": 1}
    assert dim["evidenceDate"] == "2026-08-01T10:00:00"


def test_summary_and_scoring_pass_through(rows_stub):
    result = compare.build_compare_summary(rows_stub, "proj-a")
    assert result["project"] == "proj-a"
    assert result["summary"]["numericAverage"] == 7.0
    assert result["scoring"] == {"customFormula": False}
    assert result["runsCount"] == 1
    assert result["lastRun"] == {"runId": "run-1", "dateLabel": "01 Aug", "status": RunState.DONE}
    assert _Rows.loaded == [(rows_stub, "proj-a")]


def test_trend_detail_keeps_only_dimension_and_score(rows_stub):
    result = compare.build_compare_summary(rows_stub, "proj-a")
    entry = result["trend"][0]
    assert entry["numericAverage"] == 7.0
    assert entry["dimensionDetails"] == [{"dimension": "Security", "score": 7.0}]


def test_unknown_project_returns_none(rows_stub):
    assert compare.build_compare_summary(rows_stub, "ghost") is None
    assert _Rows.loaded == []


def test_parent_project_takes_the_full_path(rows_stub, monkeypatch):
    """A parent folds in its children, which live outside its rows."""
    monkeypatch.setattr(compare, "find_children", lambda root, project: ["child"])
    monkeypatch.setattr(compare, "get_project_scores", lambda root, project: {
        "accumulated": _ACCUMULATED, "trend": _TREND,
        "availableRuns": [{"runId": "run-1", "dateLabel": "01 Aug", "status": "done"}],
    })
    result = compare.build_compare_summary(rows_stub, "proj-a")
    assert result["summary"]["numericAverage"] == 7.0
    assert result["runsCount"] == 1
    assert _Rows.loaded == []


def test_no_runs_shape(rows_stub):
    result = compare.build_compare_summary(rows_stub, "empty")
    assert result["dimensions"] == []
    assert result["trend"] == []
    assert result["runsCount"] == 0
    assert result["lastRun"] is None
    assert result["summary"] == {}


def test_fleet_builds_each_project_once_and_isolates_failures(rows_stub, monkeypatch):
    real = compare.build_compare_summary

    def build(root, project):
        if project == "boom":
            raise OSError("disk")
        return real(root, project)

    monkeypatch.setattr(compare, "build_compare_summary", build)
    result = compare.build_fleet_compare(rows_stub, ["proj-a", "ghost", "boom", "proj-a", "empty"])
    assert [s["project"] for s in result["summaries"]] == ["proj-a", "empty"]
    assert result["errors"] == {"ghost": "Project not found", "boom": "Failed to load compare summary"}
    assert _Rows.loaded == [(rows_stub, "proj-a"), (rows_stub, "empty")]


def test_fleet_runs_under_one_score_cache_session(rows_stub, monkeypatch):
    entered = []

    @contextmanager
    def session():
        entered.append(True)
        yield

    monkeypatch.setattr(compare, "score_cache_session", session)
    compare.build_fleet_compare(rows_stub, ["proj-a", "empty"])
    assert entered == [True]


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


def test_summary_carries_commits_since_last_scored_run(monkeypatch, rows_stub):
    seen = {}

    def fake_commits(repo_root, since_iso):
        seen["since"] = since_iso
        return 7

    monkeypatch.setattr(compare, "local_repo_root", lambda root, project: Path("/tmp/repo"))
    monkeypatch.setattr(compare, "_commits_since", fake_commits)
    result = compare.build_compare_summary(rows_stub, "proj-a")
    assert result["commitsSinceLastRun"] == 7
    # Counted from the newest scored run's date, not the raw last run.
    assert seen["since"] == "2026-08-01T10:00:00"
