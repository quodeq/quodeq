import dataclasses
import io
from pathlib import Path

import pytest

from quodeq.assistant.adapters import _cli as _cli_mod
from quodeq.assistant.adapters._cli import CliTurnConfig, run_cli_turn
from quodeq.data.sqlite.assistant_repository import AssistantRepository


class FakeProc:
    def __init__(self, lines, returncode=0):
        self.stdout = io.StringIO("".join(l + "\n" for l in lines))
        self.stderr = io.StringIO("")
        self.returncode = returncode
        self.killed = False

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode  # scripted proc has already exited

    def kill(self):
        self.killed = True


def _config(tmp_path):
    return CliTurnConfig(provider="claude", model="sonnet", scratch_base=tmp_path,
                         mcp_server_args=["--db-path", str(tmp_path / "a.db"),
                                          "--session-id", "s1", "--evaluators-dir", str(tmp_path),
                                          "--compiled-dir", str(tmp_path),
                                          "--dimensions-file", str(tmp_path / "d.json")],
                         db_path=tmp_path / "a.db")


def _repo(tmp_path):
    repo = AssistantRepository(tmp_path / "a.db")
    repo.create_session(session_id="s1", provider="claude", model="sonnet")
    return repo


def test_streams_tokens_and_captures_session_id(tmp_path):
    repo = _repo(tmp_path)
    lines = [
        '{"type": "system", "session_id": "claude-uuid-1"}',
        '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}}',
        '{"type": "result", "result": "Hello", "session_id": "claude-uuid-1"}',
    ]
    frames = []
    text = run_cli_turn(
        messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        config=_config(tmp_path), session_id="s1", prior_session_id=None,
        repository=repo, emit=frames.append,
        spawn_fn=lambda argv, *, cwd, env: FakeProc(lines))
    assert text == "Hello"
    assert {"type": "token", "text": "Hello"} in frames
    assert repo.get_session("s1")["cli_session_id"] == "claude-uuid-1"


def test_result_echo_of_streamed_text_is_not_emitted_twice(tmp_path):
    repo = _repo(tmp_path)
    lines = [
        '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}}',
        '{"type": "result", "result": "Hello", "session_id": "claude-uuid-1"}',
    ]
    frames = []
    text = run_cli_turn(
        messages=[{"role": "user", "content": "hi"}],
        config=_config(tmp_path), session_id="s1", prior_session_id=None,
        repository=repo, emit=frames.append,
        spawn_fn=lambda argv, *, cwd, env: FakeProc(lines))
    assert text == "Hello"
    token_frames = [f for f in frames if f == {"type": "token", "text": "Hello"}]
    assert len(token_frames) == 1


def test_result_only_text_is_still_emitted(tmp_path):
    repo = _repo(tmp_path)
    lines = [
        '{"type": "result", "result": "Hi"}',
    ]
    frames = []
    text = run_cli_turn(
        messages=[{"role": "user", "content": "hi"}],
        config=_config(tmp_path), session_id="s1", prior_session_id=None,
        repository=repo, emit=frames.append,
        spawn_fn=lambda argv, *, cwd, env: FakeProc(lines))
    assert text == "Hi"
    assert {"type": "token", "text": "Hi"} in frames


def test_result_with_differing_text_is_emitted(tmp_path):
    repo = _repo(tmp_path)
    lines = [
        '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Step 1 done"}]}}',
        '{"type": "result", "result": "Final answer: X", "session_id": "claude-uuid-1"}',
    ]
    frames = []
    text = run_cli_turn(
        messages=[{"role": "user", "content": "hi"}],
        config=_config(tmp_path), session_id="s1", prior_session_id=None,
        repository=repo, emit=frames.append,
        spawn_fn=lambda argv, *, cwd, env: FakeProc(lines))
    token_texts = [f["text"] for f in frames if f["type"] == "token"]
    assert token_texts == ["Step 1 done", "Final answer: X"]
    assert text == "Final answer: X"


def test_tool_use_emits_frame(tmp_path):
    repo = _repo(tmp_path)
    lines = [
        '{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "get_scores", "input": {}}]}}',
        '{"type": "result", "result": "done"}',
    ]
    frames = []
    run_cli_turn(messages=[{"role": "user", "content": "scores?"}], config=_config(tmp_path),
                 session_id="s1", prior_session_id=None, repository=repo,
                 emit=frames.append, spawn_fn=lambda argv, *, cwd, env: FakeProc(lines))
    assert any(f["type"] == "tool_call" and f["name"] == "get_scores" for f in frames)


def test_resume_failure_triggers_replay_fallback(tmp_path):
    repo = _repo(tmp_path)
    repo.set_cli_session_id("s1", "old-uuid")
    repo.add_message("s1", "user", "earlier")
    repo.add_message("s1", "assistant", "earlier answer")
    calls = []

    def spawn(argv, *, cwd, env):
        calls.append(argv)
        if len(calls) == 1:
            return FakeProc([], returncode=1)  # resume attempt fails
        return FakeProc(['{"type": "result", "result": "recovered"}'])  # replay succeeds

    frames = []
    text = run_cli_turn(messages=[{"role": "system", "content": "sys"},
                                  {"role": "user", "content": "earlier"},
                                  {"role": "assistant", "content": "earlier answer"},
                                  {"role": "user", "content": "again"}],
                        config=_config(tmp_path), session_id="s1",
                        prior_session_id="old-uuid", repository=repo,
                        emit=frames.append, spawn_fn=spawn)
    assert text == "recovered"
    assert len(calls) == 2
    assert calls[0] != calls[1]  # first used --resume, second rebuilt
    assert any(f["type"] == "warning" and "rebuilt" in f["message"] for f in frames)


def test_nonzero_exit_with_output_does_not_replay(tmp_path):
    repo = _repo(tmp_path)
    repo.set_cli_session_id("s1", "old-uuid")
    calls = []

    def spawn(argv, *, cwd, env):
        calls.append(argv)
        return FakeProc(['{"type": "result", "result": "ok"}'], returncode=1)

    frames = []
    text = run_cli_turn(messages=[{"role": "user", "content": "hi"}], config=_config(tmp_path),
                        session_id="s1", prior_session_id="old-uuid", repository=repo,
                        emit=frames.append, spawn_fn=spawn)
    assert text == "ok"  # non-empty answer is success despite rc=1
    assert len(calls) == 1  # no replay
    assert not any(f["type"] == "warning" for f in frames)


def test_empty_output_raises(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(RuntimeError):
        run_cli_turn(messages=[{"role": "user", "content": "hi"}], config=_config(tmp_path),
                     session_id="s1", prior_session_id=None, repository=repo,
                     emit=lambda f: None, spawn_fn=lambda argv, *, cwd, env: FakeProc([]))


def test_web_enabled_reaches_spawned_argv(tmp_path):
    repo = _repo(tmp_path)
    base = _config(tmp_path)
    config = CliTurnConfig(provider=base.provider, model=base.model,
                           scratch_base=base.scratch_base,
                           mcp_server_args=base.mcp_server_args,
                           db_path=base.db_path, web_enabled=True)
    captured = {}

    def spawn(argv, *, cwd, env):
        captured["argv"] = argv
        return FakeProc(['{"type": "result", "result": "ok"}'])

    run_cli_turn(messages=[{"role": "user", "content": "hi"}], config=config,
                 session_id="s1", prior_session_id=None, repository=repo,
                 emit=lambda f: None, spawn_fn=spawn)
    allowed = captured["argv"][captured["argv"].index("--allowedTools") + 1]
    assert "WebSearch" in allowed and "WebFetch" in allowed


def test_web_disabled_by_default_in_spawned_argv(tmp_path):
    repo = _repo(tmp_path)
    captured = {}

    def spawn(argv, *, cwd, env):
        captured["argv"] = argv
        return FakeProc(['{"type": "result", "result": "ok"}'])

    run_cli_turn(messages=[{"role": "user", "content": "hi"}], config=_config(tmp_path),
                 session_id="s1", prior_session_id=None, repository=repo,
                 emit=lambda f: None, spawn_fn=spawn)
    assert captured["argv"][captured["argv"].index("--allowedTools") + 1] == "mcp__quodeq-assistant"


def _capture_spawn(captured, lines):
    def spawn(argv, cwd=None, env=None):
        captured["argv"] = argv
        return FakeProc(lines)
    return spawn


def test_claude_system_prompt_reaches_argv(tmp_path):
    repo = _repo(tmp_path)
    captured = {}
    cfg = dataclasses.replace(_config(tmp_path), system_prompt="CTX", skill_block="")
    run_cli_turn(
        messages=[{"role": "system", "content": "CTX"},
                  {"role": "user", "content": "hi"}],
        config=cfg, session_id="s1", prior_session_id=None, repository=repo,
        emit=lambda f: None,
        spawn_fn=_capture_spawn(captured, ['{"type": "result", "result": "ok"}']))
    i = captured["argv"].index("--append-system-prompt")
    assert captured["argv"][i + 1] == "CTX"
    assert captured["argv"][-1] == "hi"  # skill never prefixes argv-append prompts


def test_message_prefix_provider_gets_skill_block(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    captured = {}
    base = _cli_mod.load_cli_chat_config("claude")
    monkeypatch.setattr(_cli_mod, "load_cli_chat_config",
                        lambda p: dataclasses.replace(base, system_prompt_style="message-prefix"))
    cfg = dataclasses.replace(_config(tmp_path), system_prompt="CTX",
                              skill_block="[skill:x]\nDo X")
    run_cli_turn(
        messages=[{"role": "system", "content": "CTX"},
                  {"role": "user", "content": "hi"}],
        config=cfg, session_id="s1", prior_session_id=None, repository=repo,
        emit=lambda f: None,
        spawn_fn=_capture_spawn(captured, ['{"type": "result", "result": "ok"}']))
    assert captured["argv"][-1] == "[skill:x]\nDo X\n\nhi"
    assert "--append-system-prompt" not in captured["argv"]
