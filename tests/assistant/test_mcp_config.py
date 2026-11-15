import json
import subprocess
import sys

import pytest

from quodeq.assistant.mcp import mcp_config
from quodeq.assistant.mcp.mcp_config import register_cli_mcp, write_mcp_config


def test_write_mcp_config_shape(tmp_path):
    path = tmp_path / "mcp.json"
    write_mcp_config(["--db-path", "/x/assistant.db", "--session-id", "s1"], path)
    data = json.loads(path.read_text())
    server = data["mcpServers"]["quodeq-assistant"]
    assert server["command"] == sys.executable
    assert server["args"][:2] == ["-m", "quodeq.assistant.mcp.server"]
    assert "--session-id" in server["args"]
    # 0600 perms — POSIX only. os.chmod's mode bits are a no-op on Windows
    # (st_mode reads 0o666), so only assert the hardening where it applies.
    if sys.platform != "win32":
        assert (path.stat().st_mode & 0o777) == 0o600


def test_codex_mcp_config_arg_is_valid_toml():
    import tomllib
    arg = mcp_config.codex_mcp_config_arg(["--db-path", "/x/a.db", "--session-id", "s1"])
    assert arg.startswith("mcp_servers.quodeq-assistant=")
    server = tomllib.loads(arg)["mcp_servers"]["quodeq-assistant"]
    assert server["command"] == sys.executable
    assert server["args"][:2] == ["-m", "quodeq.assistant.mcp.server"]
    assert "--db-path" in server["args"] and "/x/a.db" in server["args"]
    assert "--session-id" in server["args"] and "s1" in server["args"]


def test_codex_mcp_config_arg_escapes_special_chars():
    import tomllib
    # a path with a space and a backslash must survive the TOML round-trip
    arg = mcp_config.codex_mcp_config_arg(["--db-path", "/x y/a\\b.db"])
    server = tomllib.loads(arg)["mcp_servers"]["quodeq-assistant"]
    assert "/x y/a\\b.db" in server["args"]


def test_unregister_cli_mcp_removes_under_the_lock(monkeypatch):
    """Public unregister must serialize under _lock while it runs `mcp remove`."""
    calls = []
    held = {"during": False}

    def _fake_run(*a, **k):
        held["during"] = mcp_config._lock.locked()
        calls.append(a[0])

    monkeypatch.setattr(mcp_config.subprocess, "run", _fake_run)

    mcp_config.unregister_cli_mcp("codex")

    assert held["during"] is True  # lock held while removing
    assert calls == [["codex", "mcp", "remove", "quodeq-assistant"]]


def test_register_cli_mcp_wraps_subprocess_failure(monkeypatch):
    def _boom(*a, **kw):
        raise subprocess.CalledProcessError(1, a[0])
    monkeypatch.setattr(subprocess, "run", _boom)
    with pytest.raises(RuntimeError, match="Could not register"):
        register_cli_mcp("claude", [])


# The desktop bundle's sys.executable is Quodeq itself, so `-m <module>` would
# reach the dashboard CLI; every path must use the private flag there.
_SERVER_ARGS = ["--db-path", "/x/a.db", "--session-id", "s1"]
_BUNDLE_ARGV = [sys.executable, "--_mcp_assistant", *_SERVER_ARGS]


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)


def test_write_mcp_config_frozen_uses_the_private_flag(tmp_path, frozen):
    path = tmp_path / "mcp.json"
    write_mcp_config(_SERVER_ARGS, path)
    server = json.loads(path.read_text())["mcpServers"]["quodeq-assistant"]
    assert [server["command"], *server["args"]] == _BUNDLE_ARGV


def test_codex_mcp_config_arg_frozen_uses_the_private_flag(frozen):
    import tomllib
    arg = mcp_config.codex_mcp_config_arg(_SERVER_ARGS)
    server = tomllib.loads(arg)["mcp_servers"]["quodeq-assistant"]
    assert [server["command"], *server["args"]] == _BUNDLE_ARGV


def _registered_cmd(monkeypatch) -> list[str]:
    calls = []
    monkeypatch.setattr(mcp_config.subprocess, "run", lambda cmd, **_kw: calls.append(cmd))
    register_cli_mcp("codex", _SERVER_ARGS)
    return calls[-1]


def test_register_cli_mcp_frozen_uses_the_private_flag(monkeypatch, frozen):
    cmd = _registered_cmd(monkeypatch)
    assert cmd[cmd.index("--") + 1:] == _BUNDLE_ARGV


def test_register_cli_mcp_from_source_runs_the_module(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    cmd = _registered_cmd(monkeypatch)
    assert cmd[cmd.index("--") + 1:] == [
        sys.executable, "-m", "quodeq.assistant.mcp.server", *_SERVER_ARGS]
