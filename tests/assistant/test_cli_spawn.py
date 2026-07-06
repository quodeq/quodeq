import subprocess
import sys
from pathlib import Path

import pytest

from quodeq.assistant.adapters import _cli_spawn
from quodeq.assistant.adapters._cli_spawn import (
    assert_no_dangerous_args, build_chat_env, external_sandbox_prefix,
    scratch_cwd, spawn_turn,
)


def _wrapped_codex(*extra):
    # a codex argv wrapped in an external sandbox launcher, shell tool removed
    return ["sandbox-exec", "-f", "/tmp/p.sb", "codex", "exec",
            "--dangerously-bypass-approvals-and-sandbox", "--disable", "shell_tool",
            *extra, "prompt"]


def test_bypass_allowed_only_when_externally_sandboxed_and_shell_disabled():
    assert_no_dangerous_args(_wrapped_codex())  # must NOT raise
    # unwrapped bypass (no external sandbox launcher) -> forbidden
    with pytest.raises(AssertionError):
        assert_no_dangerous_args(
            ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox",
             "--disable", "shell_tool", "prompt"])
    # wrapped but shell tool NOT disabled -> forbidden
    with pytest.raises(AssertionError):
        assert_no_dangerous_args(
            ["sandbox-exec", "-f", "/tmp/p.sb", "codex", "exec",
             "--dangerously-bypass-approvals-and-sandbox", "prompt"])


def test_other_skip_flags_forbidden_even_when_wrapped():
    # only the sandbox bypass is conditionally allowed; the claude/gemini
    # permission skips are never acceptable, wrapper or not.
    for bad in (["sandbox-exec", "-f", "/tmp/p.sb", "claude",
                 "--dangerously-skip-permissions", "--disable", "shell_tool"],
                ["bwrap", "gemini", "--yolo", "--disable", "shell_tool"]):
        with pytest.raises(AssertionError):
            assert_no_dangerous_args(bad)


def test_seatbelt_profile_denies_writes_except_allowed():
    prof = _cli_spawn._seatbelt_profile(
        writable_dirs=["/scratch/x", "/home/u/.codex"],
        writable_files=["/data/a.db", "/data/a.db-wal"])
    assert "(deny file-write*)" in prof
    assert '(subpath "/scratch/x")' in prof
    assert '(subpath "/home/u/.codex")' in prof
    assert '(literal "/data/a.db")' in prof
    assert '(literal "/data/a.db-wal")' in prof
    assert "(allow default)" in prof  # reads allowed


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="sandbox-exec is macOS-only; on Windows the real tmp_path embeds "
           "backslashes that the seatbelt profile escapes (C:\\\\... vs C:\\...), "
           "so the raw-path substring check fails on a scenario that never "
           "occurs in production.",
)
def test_external_sandbox_prefix_macos(monkeypatch, tmp_path):
    monkeypatch.setattr(_cli_spawn.platform, "system", lambda: "Darwin")
    prefix, cleanup = external_sandbox_prefix(
        writable_dirs=[str(tmp_path / "scratch")], writable_files=[str(tmp_path / "a.db")])
    assert prefix[0] == "sandbox-exec" and prefix[1] == "-f"
    profile_path = Path(prefix[2])
    assert profile_path.exists()
    body = profile_path.read_text()
    assert "(deny file-write*)" in body
    assert str(tmp_path / "scratch") in body
    cleanup()
    assert not profile_path.exists()


def test_external_sandbox_prefix_linux_bwrap(monkeypatch):
    monkeypatch.setattr(_cli_spawn.platform, "system", lambda: "Linux")
    monkeypatch.setattr(_cli_spawn.shutil, "which",
                        lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    prefix, cleanup = external_sandbox_prefix(
        writable_dirs=["/home/u/.quodeq/scratch"], writable_files=["/home/u/.quodeq/a.db"])
    assert prefix[0] == "bwrap"
    assert "--ro-bind" in prefix and "/" in prefix
    assert "--bind" in prefix  # writable dirs bound rw
    cleanup()  # no-op, must not raise


def test_external_sandbox_prefix_linux_no_sandbox_fails_safe(monkeypatch):
    monkeypatch.setattr(_cli_spawn.platform, "system", lambda: "Linux")
    monkeypatch.setattr(_cli_spawn.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="sandbox"):
        external_sandbox_prefix(writable_dirs=["/x"], writable_files=[])


def test_external_sandbox_prefix_unsupported_platform_fails_safe(monkeypatch):
    monkeypatch.setattr(_cli_spawn.platform, "system", lambda: "Windows")
    with pytest.raises(RuntimeError):
        external_sandbox_prefix(writable_dirs=["/x"], writable_files=[])


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


def test_spawn_turn_merges_stderr_into_stdout(tmp_path, monkeypatch):
    captured = {}

    class _P:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)
            self.stdout = None

    monkeypatch.setattr(subprocess, "Popen", _P)
    spawn_turn(["claude", "-p", "hi"], cwd=scratch_cwd(tmp_path), env={})
    assert captured["stderr"] is subprocess.STDOUT


def test_spawn_turn_streams_stdout(tmp_path):
    # a trivial process that emits two lines then exits
    argv = [sys.executable, "-c", "print('a'); print('b')"]
    proc = spawn_turn(argv, cwd=scratch_cwd(tmp_path), env=build_chat_env({"PATH": __import__("os").environ.get("PATH", "")}))
    out = proc.stdout.read()
    proc.wait(timeout=10)
    assert "a" in out and "b" in out
    assert proc.returncode == 0
