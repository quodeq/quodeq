import subprocess
import sys
from pathlib import Path

import pytest

from quodeq.assistant.adapters._cli_spawn import (
    assert_no_dangerous_args, build_chat_env, scratch_cwd, spawn_turn,
)


def test_env_is_allowlisted():
    env = build_chat_env({
        "PATH": "/usr/bin", "HOME": "/home/x",
        "ANTHROPIC_API_KEY": "sk-x", "QUODEQ_API_KEY": "q",
        "JIRA_API_TOKEN": "t", "GH_TOKEN": "gh", "AWS_SECRET_ACCESS_KEY": "aws",
        "LC_ALL": "en_US.UTF-8",
    })
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/home/x"
    assert env["LC_ALL"] == "en_US.UTF-8"
    for leaked in ("ANTHROPIC_API_KEY", "QUODEQ_API_KEY", "JIRA_API_TOKEN",
                   "GH_TOKEN", "AWS_SECRET_ACCESS_KEY"):
        assert leaked not in env


def test_env_omits_unlisted_keys_even_when_benign():
    # Only the allowlisted keys (+ LC_*) survive -- anything else is dropped,
    # not just a hand-picked denylist of "known sensitive" names.
    env = build_chat_env({"PATH": "/usr/bin", "RANDOM_APP_VAR": "whatever"})
    assert "PATH" in env
    assert "RANDOM_APP_VAR" not in env


def test_scratch_cwd_is_empty_and_not_repo(tmp_path):
    cwd = scratch_cwd(tmp_path)
    assert cwd.is_dir()
    assert list(cwd.iterdir()) == []
    assert cwd != tmp_path


def test_scratch_cwd_is_unique_per_call(tmp_path):
    # Two concurrent turns must not share one cwd -- one turn's cleanup must
    # never destroy another turn's scratch dir.
    cwd1 = scratch_cwd(tmp_path)
    cwd2 = scratch_cwd(tmp_path)
    assert cwd1 != cwd2
    assert cwd1.is_dir() and cwd2.is_dir()
    assert cwd1.parent == Path(tmp_path)
    assert cwd2.parent == Path(tmp_path)


def test_dangerous_args_guard():
    assert_no_dangerous_args(["claude", "-p", "hi"])  # ok
    for bad in (["claude", "--permission-mode", "bypassPermissions"],
                ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox"],
                ["gemini", "--yolo"],
                ["claude", "--dangerously-skip-permissions"]):
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


def test_scratch_cwd_each_call_is_fresh_and_empty(tmp_path):
    # Every call gets its own unique, empty dir under base -- concurrent turns
    # never share (or clobber) one another's scratch cwd.
    cwd = scratch_cwd(tmp_path)
    (cwd / "stale.txt").write_text("leftover")
    cwd2 = scratch_cwd(tmp_path)
    assert cwd2 != cwd
    assert cwd2.is_dir()
    assert list(cwd2.iterdir()) == []
    assert Path(tmp_path) in cwd2.parents


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
