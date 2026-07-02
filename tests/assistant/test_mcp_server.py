import io
import json

from quodeq.assistant.mcp import server
from quodeq.assistant.tools._registry import ToolRegistry, ToolSpec


def _registry():
    reg = ToolRegistry()
    reg.register(ToolSpec("get_scores", "scores", {"type": "object", "properties": {}},
                          lambda: {"security": {"grade": "C"}}))
    return reg


def _run(requests):
    stdin = io.StringIO("".join(json.dumps(r) + "\n" for r in requests))
    stdout = io.StringIO()
    stderr = io.StringIO()
    server.serve(_registry(), stdin=stdin, stdout=stdout, stderr=stderr)
    return [json.loads(l) for l in stdout.getvalue().splitlines() if l.strip()]


def test_initialize_and_tools_list():
    out = _run([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ])
    init, tools = out[0], out[1]
    assert init["result"]["serverInfo"]["name"] == "quodeq-assistant"
    names = [t["name"] for t in tools["result"]["tools"]]
    assert "get_scores" in names
    assert "inputSchema" in tools["result"]["tools"][0]


def test_tools_call_dispatches_registry():
    out = _run([{"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "get_scores", "arguments": {}}}])
    result = out[0]["result"]
    assert result["isError"] is False
    assert "security" in result["content"][0]["text"]


def test_tools_call_unknown_tool_is_error():
    out = _run([{"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                 "params": {"name": "nope", "arguments": {}}}])
    assert out[0]["result"]["isError"] is True
