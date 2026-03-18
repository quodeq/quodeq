"""Stream validation helpers for AI CLI stream-json output."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.shared.logging import log_debug
from quodeq.shared.utils import open_text

_MCP_SERVER_NAME = "findings"


def get_mcp_status(stream_file: Path) -> str | None:
    """Return MCP server status from the stream init event, or None if unavailable."""
    if not stream_file.exists() or stream_file.stat().st_size == 0:
        return None
    try:
        with open_text(stream_file) as f:
            first = f.readline().strip()
            if not first:
                return None
            d = json.loads(first)
            for srv in d.get("mcp_servers", []):
                if srv.get("name") == _MCP_SERVER_NAME:
                    return srv.get("status")
    except (json.JSONDecodeError, OSError) as exc:
        log_debug(f"Failed to read MCP status from {stream_file}: {exc}")
    return None


def is_stream_valid(stream_file: Path) -> bool:
    """Return True if stream exists, is non-empty, and has no error events."""
    if not stream_file.exists() or stream_file.stat().st_size == 0:
        return False
    try:
        with open_text(stream_file) as f:
            for line in f:
                try:
                    d = json.loads(line.strip())
                    if d.get("type") == "result" and d.get("is_error"):
                        return False
                except json.JSONDecodeError as exc:
                    log_debug(f"Skipping malformed stream line in {stream_file}: {exc}")
    except OSError as exc:
        log_debug(f"Cannot read stream file {stream_file}: {exc}")
        return False
    return True
