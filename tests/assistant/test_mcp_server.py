import io
import json

from quodeq.assistant.mcp import server
from quodeq.assistant.tools._registry import ToolRegistry, ToolSpec


def test_build_registry_from_args_parses_project_scope(tmp_path):
    args = [
        "--db-path", str(tmp_path / "a.db"), "--session-id", "s1",
        "--evaluators-dir", str(tmp_path / "e"),
        "--compiled-dir", str(tmp_path / "c"),
        "--dimensions-file", str(tmp_path / "d.json"),
        "--project-id", "selectives", "--reports-dir", str(tmp_path / "reports"),
    ]
    parser = server.argparse.ArgumentParser()
    for a in ("--db-path", "--session-id", "--run-dir", "--repo-root",
              "--evaluators-dir", "--compiled-dir", "--dimensions-file",
              "--project-id", "--reports-dir"):
        parser.add_argument(a, default="")
    ns = parser.parse_args(args)
    registry = server._build_registry_from_args(ns)
    assert "get_overview" in registry.names()


def test_build_registry_defaults_reports_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("quodeq.shared._env.get_evaluations_dir",
                        lambda: str(tmp_path / "evals"))
    parser = server.argparse.ArgumentParser()
    for a in ("--db-path", "--session-id", "--run-dir", "--repo-root",
              "--evaluators-dir", "--compiled-dir", "--dimensions-file",
              "--project-id", "--reports-dir"):
        parser.add_argument(a, default="")
    ns = parser.parse_args([
        "--db-path", str(tmp_path / "a.db"), "--session-id", "s1",
        "--evaluators-dir", str(tmp_path / "e"),
        "--compiled-dir", str(tmp_path / "c"),
        "--dimensions-file", str(tmp_path / "d.json"),
    ])
    # No --reports-dir → falls back to get_evaluations_dir(); must not raise.
    assert server._build_registry_from_args(ns).names()


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


def test_dispatch_exception_answers_with_error_frame():
    reg = _registry()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("kaboom")

    reg.dispatch = _boom  # force the dispatch path to raise
    stdin = io.StringIO(json.dumps(
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
         "params": {"name": "get_scores", "arguments": {}}}) + "\n")
    stdout, stderr = io.StringIO(), io.StringIO()
    server.serve(reg, stdin=stdin, stdout=stdout, stderr=stderr)
    frames = [json.loads(l) for l in stdout.getvalue().splitlines() if l.strip()]
    assert len(frames) == 1
    assert frames[0]["id"] == 7
    assert frames[0]["error"]["code"] == -32603
    assert "kaboom" in frames[0]["error"]["message"]
