from quodeq.assistant.adapters._fallback import extract_prompted_tool_call


def test_extracts_fenced_json_tool_call():
    text = 'Let me search.\n```json\n{"tool_call": {"name": "search_findings", "arguments": {"query": "sql"}}}\n```'
    assert extract_prompted_tool_call(text) == ("search_findings", {"query": "sql"})


def test_extracts_bare_json_object():
    text = '{"tool_call": {"name": "get_scores", "arguments": {}}}'
    assert extract_prompted_tool_call(text) == ("get_scores", {})


def test_plain_text_returns_none():
    assert extract_prompted_tool_call("The grade is C because...") is None
    assert extract_prompted_tool_call('{"not_a_tool_call": 1}') is None
