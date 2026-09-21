"""Stream validation helpers for AI CLI stream-json output."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.stream.events import copilot_error, copilot_event_data
from quodeq.shared.utils import open_text

_MCP_SERVER_NAME = "findings"


def _has_content(stream_file: Path) -> bool:
    """True when *stream_file* exists and holds at least one byte.

    One stat, shared by every reader here: an absent or empty stream carries
    neither an MCP status nor an error event.
    """
    return stream_file.exists() and stream_file.stat().st_size > 0


def get_mcp_status(stream_file: Path, *, log: LogSink = NULL_LOG) -> str | None:
    """Return MCP server status from the stream init event, or None if unavailable."""
    if not _has_content(stream_file):
        return None
    try:
        with open_text(stream_file) as f:
            for line in f:
                d = json.loads(line)
                if not isinstance(d, dict):
                    continue
                servers = d.get("mcp_servers", [])
                if d.get("type") == "session.mcp_servers_loaded":
                    servers = copilot_event_data(d).get("servers", [])
                if not isinstance(servers, list):
                    log.debug(f"Invalid MCP server list in {stream_file}")
                    continue
                for srv in servers:
                    if isinstance(srv, dict) and srv.get("name") == _MCP_SERVER_NAME:
                        status = srv.get("status")
                        if isinstance(status, str):
                            return status
                        log.debug(f"Invalid MCP server status in {stream_file}")
    except (json.JSONDecodeError, OSError) as exc:
        log.debug(f"Failed to read MCP status from {stream_file}: {exc}")
    return None


def _is_error_event(
    line: str, stream_file: Path, *, log: LogSink = NULL_LOG,
) -> bool | None:
    """Check if a stream line is an error event. Returns True/False or None to skip."""
    try:
        d = json.loads(line.strip())
    except json.JSONDecodeError as exc:
        log.debug(f"Skipping malformed stream line in {stream_file}: {exc}")
        return None
    if not isinstance(d, dict):
        return False  # a valid-JSON non-object line is not an error event
    if d.get("type") == "result" and d.get("is_error"):
        return True
    return copilot_error(d) is not None


def is_stream_valid(stream_file: Path, *, log: LogSink = NULL_LOG) -> bool:
    """Return True if stream exists, is non-empty, and has no error events."""
    if not _has_content(stream_file):
        return False
    try:
        with open_text(stream_file) as f:
            for line in f:
                if _is_error_event(line, stream_file, log=log) is True:
                    return False
    except OSError as exc:
        log.debug(f"Cannot read stream file {stream_file}: {exc}")
        return False
    return True
