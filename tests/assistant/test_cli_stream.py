from quodeq.assistant.adapters import _stream
from quodeq.assistant.adapters._stream import (
    assistant_text, parse_line, session_id, tool_uses,
)


def test_parse_line_bad_json():
    assert parse_line("") is None
    assert parse_line("not json") is None
    assert parse_line('{"type": "x"}') == {"type": "x"}


def test_claude_assistant_text():
    ev = {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Hello "}, {"type": "text", "text": "world"},
        {"type": "tool_use", "name": "search_findings", "input": {"query": "x"}},
    ]}}
    assert assistant_text(ev) == ["Hello ", "world"]
    assert tool_uses(ev) == ["search_findings"]


def test_claude_result_text():
    assert assistant_text({"type": "result", "result": "final answer"}) == ["final answer"]


def test_codex_item_completed_text():
    ev = {"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}}
    assert assistant_text(ev) == ["hi"]


def test_null_message_does_not_crash():
    ev = {"type": "assistant", "message": None}
    assert assistant_text(ev) == []
    assert tool_uses(ev) == []


def test_null_item_does_not_crash():
    ev = {"type": "item.completed", "item": None}
    assert assistant_text(ev) == []
    assert tool_uses(ev) == []


def test_null_content_does_not_crash():
    ev = {"type": "assistant", "message": {"content": None}}
    assert assistant_text(ev) == []
    assert tool_uses(ev) == []


def test_session_id_from_system_and_result():
    assert session_id({"type": "system", "session_id": "uuid-1"}) == "uuid-1"
    assert session_id({"type": "result", "session_id": "uuid-2"}) == "uuid-2"
    assert session_id({"type": "assistant", "message": {"content": []}}) is None
    assert session_id({"type": "session.created", "thread_id": "th-9"}) == "th-9"


def test_tool_use_details_includes_args_summary():
    event = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "get_report",
         "input": {"dimension": "security"}}]}}
    assert _stream.tool_use_details(event) == [
        {"name": "get_report", "args_summary": '{"dimension": "security"}'}]


def test_tool_use_details_empty_input_gives_empty_summary():
    event = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "get_scores", "input": {}}]}}
    assert _stream.tool_use_details(event) == [
        {"name": "get_scores", "args_summary": ""}]
