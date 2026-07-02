import json
import sys
from pathlib import Path

from quodeq.assistant.mcp import _config
from quodeq.assistant.mcp._config import write_mcp_config


def test_write_mcp_config_shape(tmp_path):
    path = tmp_path / "mcp.json"
    write_mcp_config(["--db-path", "/x/assistant.db", "--session-id", "s1"], path)
    data = json.loads(path.read_text())
    server = data["mcpServers"]["quodeq-assistant"]
    assert server["command"] == sys.executable
    assert server["args"][:2] == ["-m", "quodeq.assistant.mcp.server"]
    assert "--session-id" in server["args"]
    # 0600 perms
    assert (path.stat().st_mode & 0o777) == 0o600


def test_unregister_cli_mcp_acquires_lock_and_clears_key(monkeypatch):
    """Public unregister must serialize under _lock and drop the registered key."""
    calls = []
    held = {"during": False}

    def _fake_run(*a, **k):
        held["during"] = _config._lock.locked()
        calls.append(a[0])

    monkeypatch.setattr(_config.subprocess, "run", _fake_run)
    _config._registered.add("codex:quodeq-assistant")

    _config.unregister_cli_mcp("codex")

    assert held["during"] is True  # lock held while removing
    assert "codex:quodeq-assistant" not in _config._registered
    assert calls == [["codex", "mcp", "remove", "quodeq-assistant"]]
