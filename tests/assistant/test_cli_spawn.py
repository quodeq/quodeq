import subprocess
import sys

import pytest

from quodeq.assistant.adapters._cli_spawn import (
    SENSITIVE_ENV_KEYS, assert_no_dangerous_args, build_chat_env, scratch_cwd, spawn_turn,
)


def test_env_scrubs_secrets():
    env = build_chat_env({"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "sk-x", "QUODEQ_API_KEY": "q"})
    assert "PATH" in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "QUODEQ_API_KEY" not in env


def test_scratch_cwd_is_empty_and_not_repo(tmp_path):
    cwd = scratch_cwd(tmp_path)
    assert cwd.is_dir()
    assert list(cwd.iterdir()) == []
    assert cwd != tmp_path


def test_dangerous_args_guard():
    assert_no_dangerous_args(["claude", "-p", "hi"])  # ok
    for bad in (["claude", "--permission-mode", "bypassPermissions"],
                ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox"],
                ["gemini", "--yolo"]):
        with pytest.raises(AssertionError):
            assert_no_dangerous_args(bad)


def test_dangerous_args_guard_equals_forms():
    for bad in (["claude", "--permission-mode=bypassPermissions"],
                ["gemini", "--yolo=true"],
                ["codex", "--dangerously-bypass-approvals-and-sandbox"]):
        with pytest.raises(AssertionError):
            assert_no_dangerous_args(bad)


def test_dangerous_args_guard_benign_near_miss():
    # value mentions --yolo but is not an exact token/part -> must NOT raise
    assert_no_dangerous_args(["claude", "-p", "tell me about --yolo mode"])
    assert_no_dangerous_args(["claude", "/x/--yolo-notes"])


def test_scratch_cwd_cleared_on_reuse(tmp_path):
    cwd = scratch_cwd(tmp_path)
    (cwd / "stale.txt").write_text("leftover")
    cwd2 = scratch_cwd(tmp_path)
    assert cwd2 == cwd
    assert list(cwd2.iterdir()) == []


def test_spawn_turn_discards_stderr(tmp_path, monkeypatch):
    captured = {}

    class _P:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)
            self.stdout = None

    monkeypatch.setattr(subprocess, "Popen", _P)
    spawn_turn(["claude", "-p", "hi"], cwd=scratch_cwd(tmp_path), env={})
    assert captured["stderr"] is subprocess.DEVNULL


def test_spawn_turn_streams_stdout(tmp_path):
    # a trivial process that emits two lines then exits
    argv = [sys.executable, "-c", "print('a'); print('b')"]
    proc = spawn_turn(argv, cwd=scratch_cwd(tmp_path), env=build_chat_env({"PATH": __import__("os").environ.get("PATH", "")}))
    out = proc.stdout.read()
    proc.wait(timeout=10)
    assert "a" in out and "b" in out
    assert proc.returncode == 0
