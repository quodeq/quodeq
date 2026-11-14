"""The Codex ``-c`` override takes the server's full argv, so the bundled app
can put its own executable and private flag where the interpreter and ``-m``
go when running from source."""
from __future__ import annotations

import tomllib

from quodeq.shared.mcp import codex_mcp_override


def test_codex_override_splits_argv_into_command_and_args():
    arg = codex_mcp_override("findings", ["/Apps/Quodeq App/Quodeq", "--_mcp_findings", "C:\\run\\f.jsonl"])
    assert arg.startswith("mcp_servers.findings=")
    server = tomllib.loads(arg)["mcp_servers"]["findings"]
    assert server == {
        "command": "/Apps/Quodeq App/Quodeq",
        "args": ["--_mcp_findings", "C:\\run\\f.jsonl"],
    }
