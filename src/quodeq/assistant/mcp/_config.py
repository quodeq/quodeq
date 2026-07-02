"""Wire the assistant MCP server into a CLI (config-file for claude; register for codex/gemini)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

_SERVER_NAME = "quodeq-assistant"
_SERVER_MODULE = ["-m", "quodeq.assistant.mcp.server"]
_REGISTER_TIMEOUT_S = 10
_lock = threading.Lock()
_registered: set[str] = set()


def _server_argv(server_args: list[str]) -> list[str]:
    return [sys.executable, *_SERVER_MODULE, *server_args]


def write_mcp_config(server_args: list[str], path: Path) -> None:
    payload = {"mcpServers": {_SERVER_NAME: {
        "command": sys.executable, "args": [*_SERVER_MODULE, *server_args]}}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(path, 0o600)


def register_cli_mcp(cmd: str, server_args: list[str], *, separator: bool = True) -> None:
    key = f"{cmd}:{_SERVER_NAME}"
    with _lock:
        unregister_cli_mcp(cmd)
        register_cmd = [cmd, "mcp", "add", _SERVER_NAME]
        if separator:
            register_cmd.append("--")
        register_cmd.extend(_server_argv(server_args))
        subprocess.run(register_cmd, check=True, capture_output=True, timeout=_REGISTER_TIMEOUT_S)
        _registered.add(key)


def unregister_cli_mcp(cmd: str) -> None:
    key = f"{cmd}:{_SERVER_NAME}"
    try:
        subprocess.run([cmd, "mcp", "remove", _SERVER_NAME],
                       check=False, capture_output=True, timeout=_REGISTER_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        pass
    _registered.discard(key)
