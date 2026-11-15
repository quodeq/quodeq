"""Codex CLI MCP config helpers shared by the analysis and assistant pipelines."""
from __future__ import annotations

import json


def codex_mcp_override(server_name: str, argv: list[str]) -> str:
    """Render a ``codex exec -c`` TOML override defining an MCP server inline.

    Codex accepts single-invocation config overrides as TOML assignments,
    scoping the server to one run instead of mutating the user's global
    ``~/.codex/config.toml``. JSON string encoding is valid TOML basic-string
    syntax, so paths with spaces or backslashes round-trip without custom
    escaping. *argv* is the full server command: ``argv[0]`` becomes
    ``command`` and the rest ``args`` (see ``shared.frozen.mcp_server_cmd``).
    """
    command = json.dumps(argv[0])
    args_toml = "[" + ", ".join(json.dumps(a) for a in argv[1:]) + "]"
    return f"mcp_servers.{server_name}={{command = {command}, args = {args_toml}}}"
