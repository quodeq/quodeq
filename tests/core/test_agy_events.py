"""agy's event-keyed stream recast in the Claude shape the parsers read."""
from quodeq.core.stream.agy_events import is_agy_event, normalize_event


def _step(**fields):
    return {"event": "step_update", "step_update": {"conversation_id": "c1", **fields}}


def test_other_dialects_pass_through_unchanged():
    claude_stream_event = {"type": "stream_event", "event": {"type": "message_start"}}
    assert normalize_event(claude_stream_event) is claude_stream_event
    assert not is_agy_event(claude_stream_event)
    assert normalize_event(["not", "a", "dict"]) == ["not", "a", "dict"]


def test_init_announces_the_conversation_as_session_id():
    event = normalize_event({"event": "init", "conversation_id": "c1", "init": {"tools": []}})
    assert event == {"type": "system", "subtype": "init", "session_id": "c1"}


def test_text_delta_becomes_a_stream_text_delta():
    event = normalize_event(_step(step_type="agent_response", state="ACTIVE", text_delta="Hi"))
    assert event["event"]["delta"] == {"type": "text_delta", "text": "Hi"}


def test_mcp_call_becomes_a_namespaced_tool_use():
    event = normalize_event(_step(step_index=7, step_type="tool", state="ACTIVE", tool_name="call_mcp_tool",
                                  tool_info={"parameters": {"ServerName": "quodeq-assistant",
                                                            "ToolName": "list_runs", "Arguments": {"n": 1}}}))
    block = event["message"]["content"][0]
    assert block == {"type": "tool_use", "id": "agy-step-7",
                     "name": "mcp__quodeq-assistant__list_runs", "input": {"n": 1}}


def test_always_loaded_mcp_tool_keeps_its_server_and_tool():
    event = normalize_event(_step(step_index=5, step_type="tool", state="ACTIVE",
                                  tool_name="mcp_quodeq-findings_get_next_files",
                                  tool_info={"parameters": {"count": 2}}))
    block = event["message"]["content"][0]
    assert (block["name"], block["input"]) == ("mcp__quodeq-findings__get_next_files", {"count": 2})


def test_file_read_becomes_a_read_tool_use():
    event = normalize_event(_step(step_index=3, step_type="tool", state="ACTIVE", tool_name="read_file",
                                  tool_info={"parameters": {"Path": "/repo/a.py"}}))
    block = event["message"]["content"][0]
    assert (block["name"], block["input"]) == ("Read", {"file_path": "/repo/a.py"})


def test_tool_end_becomes_a_tool_result_with_its_outcome():
    done = normalize_event(_step(step_index=3, step_type="tool", state="DONE", tool_name="read_file"))
    failed = normalize_event(_step(step_index=4, step_type="tool", state="ERROR", tool_name="run_command"))
    assert done["message"]["content"][0] == {"type": "tool_result", "tool_use_id": "agy-step-3", "is_error": False}
    assert failed["message"]["content"][0]["is_error"] is True


def test_result_carries_answer_session_and_refusals():
    event = normalize_event({"event": "result", "result": {
        "conversation_id": "c1", "status": "SUCCESS", "response": "OK",
        "denied_actions": [{"action": "command"}]}})
    assert event == {"type": "result", "result": "OK", "session_id": "c1", "is_error": False,
                     "denied_actions": [{"action": "command"}]}
