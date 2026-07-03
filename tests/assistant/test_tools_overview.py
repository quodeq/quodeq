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
        {"dimension": "security", "overallScore": "72", "overallGrade": "C", "trend": "up"},
        {"dimension": "maintainability", "overallScore": "88", "overallGrade": "B", "trend": None},
    ],
    "summary": {
        "overallGrade": "B", "numericAverage": 80.0, "previousNumericAverage": 78.0,
        "totalViolations": 12, "totalCompliance": 40, "dimensionCount": 2,
        "severity": {"critical": 1, "major": 3, "minor": 8},
    },
}


def _ctx(tmp_path, *, project_id="selectives", reports_dir=None):
    repo = AssistantRepository(tmp_path / "assistant.db")
    return ToolContext(
        repository=repo, session_id="s1", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
        project_id=project_id,
        reports_dir=Path(reports_dir) if reports_dir is not None else tmp_path / "reports",
    )


def test_get_overview_trims_accumulated_payload(tmp_path, monkeypatch):
    seen = {}

    def fake_get_accumulated(reports_dir, project, as_of):
        seen["args"] = (reports_dir, project, as_of)
        return _ACCUMULATED

    monkeypatch.setattr("quodeq.assistant.tools._overview._fs_reports.get_accumulated",
                        fake_get_accumulated)
    out = _get_overview(_ctx(tmp_path))
    assert seen["args"] == (str(tmp_path / "reports"), "selectives", None)
    assert out["project"] == "selectives"
    assert out["dimensions"] == [
        {"dimension": "security", "score": "72", "grade": "C", "trend": "up"},
        {"dimension": "maintainability", "score": "88", "grade": "B", "trend": None},
    ]
    assert out["summary"] == {
        "overallGrade": "B", "numericAverage": 80.0, "totalViolations": 12,
        "dimensionCount": 2, "severity": {"critical": 1, "major": 3, "minor": 8},
    }


def test_get_overview_passes_as_of(tmp_path, monkeypatch):
    seen = {}

    def fake(rd, p, ao):
        seen["as_of"] = ao
        return _ACCUMULATED

    monkeypatch.setattr(
        "quodeq.assistant.tools._overview._fs_reports.get_accumulated", fake)
    _get_overview(_ctx(tmp_path), as_of="run-42")
    assert seen["as_of"] == "run-42"


def test_get_overview_requires_project_and_reports_dir(tmp_path):
    with pytest.raises(ToolError):
        _get_overview(_ctx(tmp_path, project_id=None))


def test_get_overview_tool_error_when_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr("quodeq.assistant.tools._overview._fs_reports.get_accumulated",
                        lambda *a: None)
    with pytest.raises(ToolError):
        _get_overview(_ctx(tmp_path))


def test_get_overview_registered(tmp_path):
    registry = build_registry(_ctx(tmp_path))
    assert "get_overview" in registry.names()
