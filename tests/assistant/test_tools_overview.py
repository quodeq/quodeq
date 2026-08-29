from pathlib import Path

import pytest

from quodeq.assistant.tools import build_registry
from quodeq.assistant.tools._context import ToolContext
from quodeq.assistant.tools._overview import _get_overview
from quodeq.assistant.tools._registry import ToolError
from quodeq.data.sqlite.assistant_repository import AssistantRepository

_ACCUMULATED = {
    "project": "selectives",
    "dimensions": [
        {
            "dimension": "security", "overallScore": "72", "overallGrade": "C",
            "trend": "up",
            "violations": [
                {"severity": "critical"},
                {"severity": "major"},
            ],
        },
        {
            "dimension": "clean-architecture", "overallScore": "88",
            "overallGrade": "B", "trend": None,
            "violations": [
                {"severity": "minor"},
            ],
        },
    ],
    "summary": {
        "overallGrade": "B", "numericAverage": 80.0, "previousNumericAverage": 78.0,
        "totalViolations": 12, "totalCompliance": 40, "dimensionCount": 2,
        "severity": {"critical": 1, "major": 3, "minor": 8},
    },
}


def _ctx(tmp_path, *, project_id="selectives", reports_dir=None,
          visible_standard_ids=None):
    repo = AssistantRepository(tmp_path / "assistant.db")
    return ToolContext(
        repository=repo, session_id="s1", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
        project_id=project_id,
        reports_dir=Path(reports_dir) if reports_dir is not None else tmp_path / "reports",
        visible_standard_ids=visible_standard_ids,
    )


def test_get_overview_trims_accumulated_payload(tmp_path, monkeypatch):
    seen = {}

    def fake_get_accumulated(reports_dir, project, as_of):
        seen["args"] = (reports_dir, project, as_of)
        return _ACCUMULATED

    monkeypatch.setattr("quodeq.assistant.tools._overview.get_accumulated",
                        fake_get_accumulated)
    out = _get_overview(_ctx(tmp_path))
    assert seen["args"] == (str(tmp_path / "reports"), "selectives", None)
    assert out["project"] == "selectives"
    assert out["dimensions"] == [
        {"dimension": "security", "score": "72", "grade": "C", "trend": "up"},
        {"dimension": "clean-architecture", "score": "88", "grade": "B", "trend": None},
    ]
    assert out["summary"] == {
        "overallGrade": "B", "numericAverage": 80.0, "totalViolations": 12,
        "dimensionCount": 2, "severity": {"critical": 1, "major": 3, "minor": 8},
    }
    assert out["hiddenStandardIds"] == []


def test_get_overview_passes_as_of(tmp_path, monkeypatch):
    seen = {}

    def fake(rd, p, ao):
        seen["as_of"] = ao
        return _ACCUMULATED

    monkeypatch.setattr(
        "quodeq.assistant.tools._overview.get_accumulated", fake)
    _get_overview(_ctx(tmp_path), as_of="run-42")
    assert seen["as_of"] == "run-42"


def test_get_overview_requires_project_and_reports_dir(tmp_path):
    with pytest.raises(ToolError, match="get_context"):
        _get_overview(_ctx(tmp_path, project_id=None))


def test_get_overview_tool_error_when_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr("quodeq.assistant.tools._overview.get_accumulated",
                        lambda *a: None)
    with pytest.raises(ToolError):
        _get_overview(_ctx(tmp_path))


def test_get_overview_registered(tmp_path):
    registry = build_registry(_ctx(tmp_path))
    assert "get_overview" in registry.names()


def test_overview_excludes_hidden_dimensions(tmp_path, monkeypatch):
    monkeypatch.setattr("quodeq.assistant.tools._overview.get_accumulated",
                        lambda *a: _ACCUMULATED)
    out = _get_overview(_ctx(tmp_path, visible_standard_ids=("security",)))
    assert [d["dimension"] for d in out["dimensions"]] == ["security"]
    assert out["hiddenStandardIds"] == ["clean-architecture"]


def test_overview_omits_aggregate_grade_when_filtering(tmp_path, monkeypatch):
    """The dashboard derives these from trend data in JS; recomputing them here
    would put the assistant back out of step with the screen."""
    monkeypatch.setattr("quodeq.assistant.tools._overview.get_accumulated",
                        lambda *a: _ACCUMULATED)
    out = _get_overview(_ctx(tmp_path, visible_standard_ids=("security",)))
    assert "overallGrade" not in out["summary"]
    assert "numericAverage" not in out["summary"]
    assert out["summary"]["note"]


def test_overview_recomputes_countable_aggregates(tmp_path, monkeypatch):
    monkeypatch.setattr("quodeq.assistant.tools._overview.get_accumulated",
                        lambda *a: _ACCUMULATED)
    out = _get_overview(_ctx(tmp_path, visible_standard_ids=("security",)))
    # Only the "security" dimension survives the filter (2 violations: one
    # critical, one major); "clean-architecture" (1 minor violation) is hidden.
    assert out["summary"]["dimensionCount"] == 1
    assert out["summary"]["totalViolations"] == 2
    assert out["summary"]["severity"] == {"critical": 1, "major": 1, "minor": 0}


def test_overview_keeps_full_summary_when_nothing_hidden(tmp_path, monkeypatch):
    monkeypatch.setattr("quodeq.assistant.tools._overview.get_accumulated",
                        lambda *a: _ACCUMULATED)
    out = _get_overview(_ctx(tmp_path, visible_standard_ids=None))
    assert out["summary"]["overallGrade"]
    assert out["summary"]["numericAverage"] is not None
    assert out["hiddenStandardIds"] == []
