"""Stream validation helpers for AI CLI stream-json output."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.stream.events import EVENT_TYPE_RESULT, copilot_error, copilot_event_data
from quodeq.shared.utils import open_text

_MCP_SERVER_NAME = "findings"
_EVENT_TYPE_SESSION_MCP_SERVERS_LOADED = "session.mcp_servers_loaded"  # Copilot's init-event dialect

MCP_STATUS_CONNECTED = "connected"  # get_mcp_status()'s healthy value; consumed by _dimension_steps.py


def _has_content(stream_file: Path) -> bool:
    """True when *stream_file* exists and holds at least one byte.

    One stat, shared by every reader here: an absent or empty stream carries
    neither an MCP status nor an error event.
    """
    return stream_file.exists() and stream_file.stat().st_size > 0


def _event_servers(event: dict) -> list | None:
    """The MCP server list an init event advertises, in either provider dialect."""
    if event.get("type") == _EVENT_TYPE_SESSION_MCP_SERVERS_LOADED:
        return copilot_event_data(event).get("servers", [])
    return event.get("mcp_servers", [])


def _findings_server_status(servers: list, stream_file: Path, log: LogSink) -> str | None:
    """The status string the findings server reports, or None if it is absent.

    A findings entry whose status is not a string is logged and skipped, so a
    later, well-formed entry can still answer.
    """
    for srv in servers:
        if not (isinstance(srv, dict) and srv.get("name") == _MCP_SERVER_NAME):
            continue
        status = srv.get("status")
        if isinstance(status, str):
            return status
        log.debug(f"Invalid MCP server status in {stream_file}")
    return None


def get_mcp_status(stream_file: Path, *, log: LogSink = NULL_LOG) -> str | None:
    """Return MCP server status from the stream init event, or None if unavailable."""
    if not _has_content(stream_file):
        return None
    try:
        with open_text(stream_file) as f:
            for line in f:
                d = json.loads(line)
                servers = _event_servers(d) if isinstance(d, dict) else None
                if not isinstance(servers, list):
                    if isinstance(d, dict):
                        log.debug(f"Invalid MCP server list in {stream_file}")
                    continue
                status = _findings_server_status(servers, stream_file, log)
                if status is not None:
                    return status
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
    if d.get("type") == EVENT_TYPE_RESULT and d.get("is_error"):
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
