"""The findings server serves the run's standards checklist, so no CLI reads outside the repo."""
from __future__ import annotations

from unittest.mock import MagicMock

from quodeq.analysis.mcp.handlers import handle_tools_call, handle_tools_list
from quodeq.analysis.prompts.standards_file import standards_file_path


def _names(result: dict) -> list[str]:
    return [t["name"] for t in result["result"]["tools"]]


def test_get_standards_is_listed_only_when_the_run_has_a_checklist():
    assert "get_standards" in _names(handle_tools_list(1, has_standards=True))
    assert "get_standards" not in _names(handle_tools_list(1))


def test_get_standards_returns_the_checklist_the_prompt_builder_wrote(tmp_path):
    checklist = standards_file_path(tmp_path, "security")
    checklist.write_text('[{"id": "S-INT-2"}]', encoding="utf-8")
    result = handle_tools_call(1, {"name": "get_standards"}, MagicMock(), standards_file=checklist)
    assert result["result"] == {"content": [{"type": "text", "text": '[{"id": "S-INT-2"}]'}]}


def test_a_missing_checklist_is_an_error_reply(tmp_path):
    result = handle_tools_call(1, {"name": "get_standards"}, MagicMock(),
                               standards_file=tmp_path / "gone.md")
    assert result["result"]["isError"] is True
