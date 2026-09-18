"""CLI adapter argv: resume fallback, web tools flag, system prompt and skill placement."""
import dataclasses

import pytest

from quodeq.assistant.adapters import _cli as _cli_mod
from quodeq.assistant.adapters._cli import CliTurnConfig, run_cli_turn

from ._cli_adapter_helpers import FakeProc, _config, _repo, _session


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
                        config=_config(tmp_path),
                        session=_session(repo, prior_session_id="old-uuid",
                                         emit=frames.append, spawn_fn=spawn))
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
                        session=_session(repo, prior_session_id="old-uuid",
                                         emit=frames.append, spawn_fn=spawn))
    assert text == "ok"  # non-empty answer is success despite rc=1
    assert len(calls) == 1  # no replay
    assert not any(f["type"] == "warning" for f in frames)


def test_empty_output_raises(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(RuntimeError):
        run_cli_turn(messages=[{"role": "user", "content": "hi"}], config=_config(tmp_path),
                     session=_session(repo, spawn_fn=lambda argv, *, cwd, env: FakeProc([])))


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
                 session=_session(repo, spawn_fn=spawn))
    allowed = captured["argv"][captured["argv"].index("--allowedTools") + 1]
    assert "WebSearch" in allowed and "WebFetch" in allowed


def test_web_disabled_by_default_in_spawned_argv(tmp_path):
    repo = _repo(tmp_path)
    captured = {}

    def spawn(argv, *, cwd, env):
        captured["argv"] = argv
        return FakeProc(['{"type": "result", "result": "ok"}'])

    run_cli_turn(messages=[{"role": "user", "content": "hi"}], config=_config(tmp_path),
                 session=_session(repo, spawn_fn=spawn))
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
        config=cfg,
        session=_session(repo, spawn_fn=_capture_spawn(
            captured, ['{"type": "result", "result": "ok"}'])))
    i = captured["argv"].index("--append-system-prompt")
    assert captured["argv"][i + 1] == "CTX"
    assert captured["argv"][-1] == "hi"  # skill never prefixes argv-append prompts


def _message_prefix(monkeypatch):
    base = _cli_mod.load_cli_chat_config("claude")
    monkeypatch.setattr(_cli_mod, "load_cli_chat_config",
                        lambda p: dataclasses.replace(base, system_prompt_style="message-prefix"))


def test_message_prefix_provider_gets_system_prompt_on_fresh_session(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    captured = {}
    _message_prefix(monkeypatch)
    cfg = dataclasses.replace(_config(tmp_path), system_prompt="QUODEQ CTX", skill_block="")
    run_cli_turn(
        messages=[{"role": "system", "content": "QUODEQ CTX"},
                  {"role": "user", "content": "hi"}],
        config=cfg,
        session=_session(repo, spawn_fn=_capture_spawn(
            captured, ['{"type": "result", "result": "ok"}'])))
    assert captured["argv"][-1] == "QUODEQ CTX\n\nhi"
    assert "--append-system-prompt" not in captured["argv"]


def test_message_prefix_provider_omits_system_prompt_on_resume(tmp_path, monkeypatch):
    # A resumed session already carries the system prompt from its first turn,
    # so re-sending it every turn would bloat the message needlessly.
    repo = _repo(tmp_path)
    captured = {}
    _message_prefix(monkeypatch)
    cfg = dataclasses.replace(_config(tmp_path), system_prompt="QUODEQ CTX", skill_block="")
    run_cli_turn(
        messages=[{"role": "user", "content": "hi"}],
        config=cfg,
        session=_session(repo, prior_session_id="th-1", spawn_fn=_capture_spawn(
            captured, ['{"type": "result", "result": "ok"}'])))
    assert captured["argv"][-1] == "hi"


def test_message_prefix_provider_prepends_system_prompt_then_skill(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    captured = {}
    _message_prefix(monkeypatch)
    cfg = dataclasses.replace(_config(tmp_path), system_prompt="CTX",
                              skill_block="[skill:x]\nDo X")
    run_cli_turn(
        messages=[{"role": "system", "content": "CTX"},
                  {"role": "user", "content": "hi"}],
        config=cfg,
        session=_session(repo, spawn_fn=_capture_spawn(
            captured, ['{"type": "result", "result": "ok"}'])))
    assert captured["argv"][-1] == "CTX\n\n[skill:x]\nDo X\n\nhi"
    assert "--append-system-prompt" not in captured["argv"]
