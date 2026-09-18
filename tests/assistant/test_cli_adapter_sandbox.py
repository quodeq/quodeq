"""CLI adapter: codex OS sandbox wrapping and error-line surfacing."""
import dataclasses
from pathlib import Path

import pytest

from quodeq.assistant.adapters import _cli as _cli_mod
from quodeq.assistant.adapters._cli import run_cli_turn

from ._cli_adapter_helpers import FakeProc, _config, _repo, _session


def test_codex_turn_is_wrapped_in_external_os_sandbox(tmp_path, monkeypatch):
    import quodeq.assistant.adapters._cli_spawn as sb
    monkeypatch.setattr(sb.platform, "system", lambda: "Darwin")  # force sandbox-exec path
    repo = _repo(tmp_path)
    cfg = dataclasses.replace(_config(tmp_path), provider="codex", model="5",
                              system_prompt="CTX")
    captured = {}

    def spawn(argv, *, cwd, env):
        captured["argv"] = argv
        captured["profile_exists_at_spawn"] = Path(argv[2]).exists()
        return FakeProc(['{"type": "thread.started", "thread_id": "th-1"}',
                         '{"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}'])

    text = run_cli_turn(
        messages=[{"role": "system", "content": "CTX"}, {"role": "user", "content": "hi"}],
        config=cfg, session=_session(repo, spawn_fn=spawn))
    argv = captured["argv"]
    assert text == "ok"
    assert argv[0] == "sandbox-exec" and argv[1] == "-f"
    assert "codex" in argv and "exec" in argv
    assert "--dangerously-bypass-approvals-and-sandbox" in argv
    di = argv.index("--disable")
    assert argv[di + 1] == "shell_tool"
    assert captured["profile_exists_at_spawn"] is True
    # the temp Seatbelt profile is cleaned up after the turn
    assert not Path(argv[2]).exists()


def _codex_sandbox_dirs(tmp_path, monkeypatch, cfg):
    seen = {}

    def spy(*, writable_dirs, writable_files):
        seen["dirs"] = writable_dirs
        return [], None

    monkeypatch.setattr(_cli_mod, "external_sandbox_prefix", spy)
    lines = ['{"type": "thread.started", "thread_id": "th-1"}',
             '{"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}']
    run_cli_turn(
        messages=[{"role": "user", "content": "hi"}],
        config=cfg,
        session=_session(_repo(tmp_path),
                         spawn_fn=lambda argv, *, cwd, env: FakeProc(lines)))
    return seen["dirs"]


def test_codex_sandbox_writable_dirs_include_worktree(tmp_path, monkeypatch):
    wt = tmp_path / "wt"
    wt.mkdir()
    cfg = dataclasses.replace(_config(tmp_path), provider="codex", model="5",
                              worktree_dir=wt)
    dirs = _codex_sandbox_dirs(tmp_path, monkeypatch, cfg)
    assert str(wt) in dirs


def test_codex_sandbox_writable_dirs_omit_worktree_when_none(tmp_path, monkeypatch):
    cfg = dataclasses.replace(_config(tmp_path), provider="codex", model="5")
    dirs = _codex_sandbox_dirs(tmp_path, monkeypatch, cfg)
    # only the scratch cwd and ~/.codex are writable on read-only turns
    assert len(dirs) == 2
    assert str(Path.home() / ".codex") in dirs


def test_json_error_event_raises_message(tmp_path):
    repo = _repo(tmp_path)
    lines = [
        '{"type": "error", "message": "{\\"type\\":\\"error\\",\\"status\\":400,\\"error\\":{\\"message\\":\\"model not supported\\"}}"}',
        '{"type": "turn.failed", "error": {"message": "turn failed"}}',
    ]
    with pytest.raises(RuntimeError, match="model not supported"):
        run_cli_turn(messages=[{"role": "user", "content": "hi"}], config=_config(tmp_path),
                     session=_session(repo, spawn_fn=lambda argv, *, cwd, env: FakeProc(lines)))


def test_non_json_cli_error_line_raises_message(tmp_path):
    repo = _repo(tmp_path)
    lines = [
        "Reading additional input from stdin...",
        "Not inside a trusted directory and --skip-git-repo-check was not specified.",
    ]
    with pytest.raises(RuntimeError, match="Not inside a trusted directory"):
        run_cli_turn(messages=[{"role": "user", "content": "hi"}], config=_config(tmp_path),
                     session=_session(repo, spawn_fn=lambda argv, *, cwd, env: FakeProc(
                         lines, returncode=1)))
