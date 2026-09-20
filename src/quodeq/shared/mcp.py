"""Codex CLI MCP config helpers shared by the analysis and assistant pipelines."""
from __future__ import annotations

import json
import sys


def codex_mcp_override(server_name: str, args: list[str]) -> str:
    """Render a ``codex exec -c`` TOML override defining an MCP server inline.

    Codex accepts single-invocation config overrides as TOML assignments,
    scoping the server to one run instead of mutating the user's global
    ``~/.codex/config.toml``. JSON string encoding is valid TOML basic-string
    syntax, so paths with spaces or backslashes round-trip without custom
    escaping. The server is launched via the current interpreter.
    """
    command = json.dumps(sys.executable)
    args_toml = "[" + ", ".join(json.dumps(a) for a in args) + "]"
    return f"mcp_servers.{server_name}={{command = {command}, args = {args_toml}}}"
