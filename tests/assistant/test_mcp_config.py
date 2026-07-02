import json
import sys
from pathlib import Path

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
