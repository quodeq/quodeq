"""The assistant driving agy: read-only argv, --conversation resume, streamed turns."""
import json
from dataclasses import replace
from unittest.mock import patch

from quodeq.assistant.adapters.cli import TurnArgvRequest, build_turn_argv, run_cli_turn
from quodeq.assistant.adapters.cli_config import load_cli_chat_config

from ._cli_adapter_helpers import FakeProc, _config, _repo, _session


def _spec(**kw):
    request = dict(prompt="hi", model="gemini-3.8-flash-high", web_enabled=False, system_prompt="",
                   mcp_config_path=None, mcp_config_arg=None, prior_session_id=None,
                   new_session_id="sid-1")
    return build_turn_argv(load_cli_chat_config("agy"), TurnArgvRequest(**{**request, **kw}))


def test_agy_turn1_parses_the_conversation_id():
    spec = _spec()
    assert spec.argv[0] == "agy"
    assert spec.argv[-2:] == ["-p", "hi"]
    assert (spec.session_id, spec.needs_id_parse) == (None, True)
    assert not {"--conversation", "--dangerously-skip-permissions", "--yolo"} & set(spec.argv)


def test_agy_turnN_resumes_with_conversation_flag():
    spec = _spec(prior_session_id="conv-1")
    assert spec.argv[spec.argv.index("--conversation") + 1] == "conv-1"
    assert spec.argv[1] != "conv-1"  # not codex's `exec resume <id>` placement
    assert spec.needs_id_parse is False


def test_agy_assistant_may_only_call_the_assistant_server():
    argv = _spec().argv
    settings = json.loads(argv[argv.index("--settings") + 1])
    assert settings["permissions"]["allow"] == ["mcp(quodeq-assistant/*)"]
    assert {"read_file(/)", "write_file(/)", "command(*)", "read_url(*)"} <= set(settings["permissions"]["deny"])


def _agy_turn(tmp_path, lines):
    repo = _repo(tmp_path)
    frames = []
    with patch("quodeq.assistant.mcp.mcp_config.register_cli_mcp"), \
         patch("quodeq.assistant.mcp.mcp_config.unregister_cli_mcp"):
        text = run_cli_turn(
            messages=[{"role": "user", "content": "hi"}],
            config=replace(_config(tmp_path), provider="agy"),
            session=_session(repo, emit=frames.append,
                             spawn_fn=lambda argv, *, cwd, env: FakeProc(lines)))
    return text, frames, repo


def _step(**fields):
    return json.dumps({"event": "step_update", "step_update": {"conversation_id": "conv-1", **fields}})


def test_agy_turn_streams_once_and_keeps_the_conversation(tmp_path):
    lines = [
        json.dumps({"event": "init", "conversation_id": "conv-1", "init": {}}),
        _step(step_type="agent_response", state="ACTIVE", text_delta="Looking. "),
        _step(step_index=2, step_type="tool", state="ACTIVE", tool_name="call_mcp_tool",
              tool_info={"parameters": {"ServerName": "quodeq-assistant", "ToolName": "list_runs"}}),
        _step(step_index=2, step_type="tool", state="DONE", tool_name="call_mcp_tool"),
        _step(step_type="agent_response", state="ACTIVE", text_delta="Two runs."),
        json.dumps({"event": "result", "result": {"conversation_id": "conv-1", "status": "SUCCESS",
                                                  "response": "Two runs."}}),
    ]
    text, frames, repo = _agy_turn(tmp_path, lines)
    assert text == "Two runs."
    assert [f["text"] for f in frames if f["type"] == "token"] == ["Looking. ", "Two runs."]
    assert any(f.get("name") == "list_runs" for f in frames if f["type"] == "tool_call")
    assert repo.get_session("s1")["cli_session_id"] == "conv-1"
