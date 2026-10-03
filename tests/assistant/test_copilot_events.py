import pytest

from quodeq.assistant.adapters import _stream
from quodeq.core.stream.events import TEXT_EXTRACTORS, copilot_error, extract_files_from_event


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


def test_copilot_structured_error_message_is_extracted():
    assert _stream.error_message({
        "type": "session.error", "data": {"message": "Model blocked by policy"},
    }) == "Model blocked by policy"
    assert _stream.error_message({"type": "result", "exitCode": 1}) is not None


def test_copilot_session_id_is_extracted():
    assert _stream.session_id({"type": "result", "sessionId": "copilot-session"}) == "copilot-session"
    assert _stream.session_id({"type": "session.start", "data": {"sessionId": "sid"}}) == "sid"


@pytest.mark.parametrize("data", [None, [], "text", {"content": 123, "arguments": []}])
def test_copilot_malformed_data_yields_no_assistant_text(data):
    assert _stream.assistant_text({"type": "assistant.message", "data": data}) == []


@pytest.mark.parametrize("data", [None, [], "text", {"content": 123, "arguments": []}])
def test_copilot_malformed_data_yields_no_partial_text(data):
    assert _stream.partial_text({"type": "assistant.message_delta", "data": data}) is None


@pytest.mark.parametrize("data", [None, [], "text", {"content": 123, "arguments": []}])
def test_copilot_malformed_data_yields_no_tool_use_details(data):
    assert _stream.tool_use_details({"type": "tool.execution_start", "data": data}) == []


@pytest.mark.parametrize("data", [None, [], "text", {"content": 123, "arguments": []}])
def test_copilot_malformed_data_yields_no_extracted_files(data):
    assert extract_files_from_event({"type": "tool.execution_start", "data": data}) == set()


@pytest.mark.parametrize("error_type", [[], {}])
def test_copilot_malformed_error_category_still_surfaces_message(error_type):
    assert _stream.error_message({
        "type": "session.error", "data": {"errorType": error_type, "message": "Provider failed"},
    }) == "Provider failed"


@pytest.mark.parametrize("server", ["findings", "quodeq-assistant"])
def test_copilot_required_mcp_policy_warning_is_fatal(server):
    event = {"type": "session.warning", "data": {
        "warningType": "mcp",
        "message": f"1 MCP server was blocked by policy: '{server}'",
    }}
    error = copilot_error(event)
    assert error is not None
    message, reason = error
    assert reason == "copilot_mcp_policy"
    assert server in message
    assert "administrator" in message
    assert _stream.error_message(event) == message


@pytest.mark.parametrize("data", [
    None, [], {"warningType": "mcp", "message": None},
    {"warningType": "mcp", "message": ["blocked by policy"]},
    {"warningType": "mcp", "message": "1 MCP server was blocked by policy: 'other'"},
    {"warningType": "mcp", "message": "Connecting to 'findings'"},
    {"warningType": "other", "message": "blocked by policy: 'findings'"},
])
def test_copilot_unrelated_or_malformed_warnings_are_not_fatal(data):
    assert copilot_error({"type": "session.warning", "data": data}) is None
