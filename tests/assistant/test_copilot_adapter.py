import json
from dataclasses import replace

import pytest

from quodeq.assistant.adapters._cli import run_cli_turn
from quodeq.assistant.orchestrator import write_safe_provider

from ._cli_adapter_helpers import FakeProc, _config, _repo, _session
from .test_cli_command import _spec


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))


def test_copilot_chat_command_and_resume():
    first = _spec("copilot", mcp_config_path="/tmp/server config.json")
    assert first.argv[first.argv.index("--additional-mcp-config") + 1] == "@/tmp/server config.json"
    assert first.argv[first.argv.index("--available-tools") + 1] == "quodeq-assistant"
    assert "--allow-all-tools" not in first.argv
    assert "--session-id" in first.argv
    assert write_safe_provider("copilot")
    resumed = _spec("copilot", prior_session_id="prior")
    assert resumed.argv[resumed.argv.index("--resume") + 1] == "prior"
    assert "--session-id" not in resumed.argv


def test_copilot_streams_reply_once_and_keeps_all_messages(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    repo = _repo(tmp_path)
    events = [
        {"type": "assistant.message_delta", "data": {"deltaContent": "Checking."}},
        {"type": "assistant.message", "data": {"content": "Checking."}},
        {"type": "tool.execution_start", "data": {"toolName": "quodeq-assistant-get_scores",
                                                  "mcpToolName": "get_scores", "arguments": {}}},
        {"type": "assistant.message_delta", "data": {"deltaContent": "Done."}},
        {"type": "assistant.message", "data": {"content": "Done."}},
        {"type": "result", "sessionId": "copilot-sid", "exitCode": 0},
    ]
    frames = []
    seen = {}

    def spawn(argv, *, cwd, env):
        assert env["COPILOT_HOME"] == str(tmp_path / ".quodeq/copilot")
        assert "--strict-mcp-config" not in argv
        from pathlib import Path
        path = Path(argv[argv.index("--additional-mcp-config") + 1][1:])
        assert json.loads(path.read_text())["mcpServers"]["quodeq-assistant"]["tools"] == ["*"]
        seen["path"] = path
        return FakeProc([json.dumps(event) for event in events])

    text = run_cli_turn(
        messages=[{"role": "user", "content": "hi"}],
        config=replace(_config(tmp_path), provider="copilot", model="auto"),
        session=_session(repo, emit=frames.append, spawn_fn=spawn),
    )
    assert text == "Checking.\n\nDone."
    assert [f["text"] for f in frames if f["type"] == "token"] == ["Checking.", "Done."]
    assert {"type": "tool_call", "name": "get_scores"} in frames
    assert repo.get_session("s1")["cli_session_id"] == "copilot-sid"
    assert not seen["path"].exists()


def test_copilot_partial_reply_with_error_is_not_success(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    events = [
        {"type": "assistant.message", "data": {"content": "Partial"}},
        {"type": "session.error", "data": {"message": "Model blocked by policy"}},
        {"type": "result", "exitCode": 1},
    ]
    with pytest.raises(RuntimeError, match="Model blocked by policy"):
        run_cli_turn(
            messages=[{"role": "user", "content": "hi"}],
            config=replace(_config(tmp_path), provider="copilot"),
            session=_session(_repo(tmp_path), spawn_fn=lambda *a, **kw: FakeProc(
                [json.dumps(e) for e in events], returncode=1)),
        )
