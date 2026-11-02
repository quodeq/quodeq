"""Stream validation helpers for AI CLI stream-json output."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.stream.agy_events import normalize_event
from quodeq.core.stream.events import (
    EVENT_TYPE_RESULT, copilot_error, copilot_event_data, parse_stream_event,
)
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
                try:
                    d = normalize_event(json.loads(line))
                except json.JSONDecodeError:
                    log.debug(f"Skipping malformed stream line in {stream_file}")
                    continue
                if not isinstance(d, dict):
                    continue
                servers = _event_servers(d)
                if not isinstance(servers, list):
                    log.debug(f"Invalid MCP server list in {stream_file}")
                    continue
                status = _findings_server_status(servers, stream_file, log)
                if status is not None:
                    return status
    except OSError as exc:
        log.debug(f"Failed to read MCP status from {stream_file}: {exc}")
    return None


def _is_error_event(
    line: str, stream_file: Path, *, log: LogSink = NULL_LOG,
) -> bool | None:
    """Check if a stream line is an error event. Returns True/False or None to skip."""
    try:
        d = normalize_event(json.loads(line.strip()))
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


def denied_actions(stream_file: Path) -> list[str]:
    """The tool actions the CLI refused without asking (agy's ``result``
    lists them). Each one an agy turn hit outside its allow and deny rules
    ended that turn early, so the run's remaining files go back to the queue."""
    names: list[str] = []
    try:
        with open_text(stream_file) as f:
            for line in f:
                event = parse_stream_event(line)
                if isinstance(event, dict) and event.get("type") == EVENT_TYPE_RESULT:
                    names += [str(_dict_get(a, "action")) for a in event.get("denied_actions") or []]
    except OSError:
        return []
    return names


def _dict_get(value: object, key: str) -> object:
    return value.get(key) if isinstance(value, dict) else value
