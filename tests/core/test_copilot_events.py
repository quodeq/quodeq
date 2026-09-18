import pytest

from quodeq.assistant.adapters import _stream
from quodeq.core.stream.events import TEXT_EXTRACTORS, extract_files_from_event


def test_copilot_complete_text_is_shared_with_analysis():
    event = {"type": "assistant.message", "data": {"content": "Analysis result"}}
    assert _stream.assistant_text(event) == ["Analysis result"]
    assert TEXT_EXTRACTORS["assistant.message"](event) == ["Analysis result"]


def test_copilot_delta():
    assert _stream.partial_text({
        "type": "assistant.message_delta", "data": {"deltaContent": "Hello"},
    }) == "Hello"


def test_copilot_tool_details():
    event = {"type": "tool.execution_start", "data": {
        "toolName": "quodeq-assistant-get_scores", "mcpToolName": "get_scores",
        "arguments": {"dimension": "security"},
    }}
    assert _stream.tool_use_details(event) == [
        {"name": "get_scores", "args_summary": '{"dimension": "security"}'},
    ]
    event["type"] = "tool.execution_complete"
    assert _stream.tool_use_details(event) == []


@pytest.mark.parametrize("tool", ["view", "grep"])
def test_copilot_file_read_progress(tool):
    event = {"type": "tool.execution_start",
             "data": {"toolName": tool, "arguments": {"path": "/repo/main.py"}}}
    assert extract_files_from_event(event) == {"/repo/main.py"}


def test_copilot_structured_error_and_session_id():
    assert _stream.error_message({
        "type": "session.error", "data": {"message": "Model blocked by policy"},
    }) == "Model blocked by policy"
    assert _stream.error_message({"type": "result", "exitCode": 1}) is not None
    assert _stream.session_id({"type": "result", "sessionId": "copilot-session"}) == "copilot-session"
    assert _stream.session_id({"type": "session.start", "data": {"sessionId": "sid"}}) == "sid"


@pytest.mark.parametrize("data", [None, [], "text", {"content": 123, "arguments": []}])
def test_copilot_malformed_event_data_is_ignored(data):
    assert _stream.assistant_text({"type": "assistant.message", "data": data}) == []
    assert _stream.partial_text({"type": "assistant.message_delta", "data": data}) is None
    assert _stream.tool_use_details({"type": "tool.execution_start", "data": data}) == []
    assert extract_files_from_event({"type": "tool.execution_start", "data": data}) == set()


@pytest.mark.parametrize("error_type", [[], {}])
def test_copilot_malformed_error_category_still_surfaces_message(error_type):
    assert _stream.error_message({
        "type": "session.error", "data": {"errorType": error_type, "message": "Provider failed"},
    }) == "Provider failed"
