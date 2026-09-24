"""Pure parsing of AI stream-json events.

Wire-format logic shared by the analysis pipeline (live progress, evidence
extraction) and the services layer (dashboard live view). It lives in core
because it is pure dict/string handling: no filesystem, no configuration,
no layer dependencies. The file-reading counters that build on it live in
``data/fs/stream_files.py``.
"""
from __future__ import annotations

import json
from typing import Callable

_TOOL_USE_TYPE = "tool_use"
_FILE_READ_TOOLS = frozenset({"Read", "Grep"})
_BLOCK_TYPE_TEXT = "text"  # Claude assistant-message content block type
_BLOCK_TYPE_OUTPUT_TEXT = "output_text"  # codex item.completed content block type
_ITEM_TYPE_AGENT_MESSAGE = "agent_message"  # codex item.completed: a complete assistant message
_WARNING_TYPE_MCP = "mcp"  # copilot session.warning's warningType for an MCP-related warning

# Stream event "type" values, compared more than once in this module (and by
# assistant/adapters/_stream.py, which reads the same wire formats).
EVENT_TYPE_ASSISTANT = "assistant"
EVENT_TYPE_ASSISTANT_MESSAGE = "assistant.message"
EVENT_TYPE_RESULT = "result"
EVENT_TYPE_ITEM_COMPLETED = "item.completed"
EVENT_TYPE_SESSION_WARNING = "session.warning"
EVENT_TYPE_SESSION_ERROR = "session.error"
EVENT_TYPE_TOOL_EXECUTION_START = "tool.execution_start"
EVENT_TYPE_ERROR = "error"
EVENT_TYPE_TURN_FAILED = "turn.failed"
# Copilot's tool-name equivalents of Claude's _FILE_READ_TOOLS.
_COPILOT_FILE_READ_TOOLS = frozenset({"view", "grep"})
# Non-retryable reason code for a Copilot MCP-policy block. Read back by
# analysis/errors.py's provider_exit_reason and services/_job_monitor_mixin.py.
COPILOT_MCP_POLICY_REASON = "copilot_mcp_policy"


def texts_from_assistant(event: dict) -> list[str]:
    """Extract text blocks from an ``assistant`` stream event."""
    texts: list[str] = []
    for block in (event.get("message") or {}).get("content") or []:
        if block.get("type") == _BLOCK_TYPE_TEXT and block.get("text"):
            texts.append(block["text"])
    return texts


def texts_from_result(event: dict) -> list[str]:
    """Extract text from a ``result`` stream event."""
    r = event.get("result")
    return [r] if r else []


def texts_from_item_completed(event: dict) -> list[str]:
    """Extract text blocks from an ``item.completed`` stream event."""
    texts: list[str] = []
    item = event.get("item") or {}
    if item.get("type") == _ITEM_TYPE_AGENT_MESSAGE:
        if item.get("text"):
            texts.append(item["text"])
        for block in item.get("content") or []:
            if block.get("type") in (_BLOCK_TYPE_TEXT, _BLOCK_TYPE_OUTPUT_TEXT) and block.get("text"):
                texts.append(block["text"])
    return texts


def copilot_event_data(event: dict) -> dict:
    """Return the object payload of a Copilot JSONL event."""
    data = event.get("data")
    return data if isinstance(data, dict) else {}


def texts_from_copilot(event: dict) -> list[str]:
    """Extract a complete Copilot assistant message, not its delta echo."""
    text = copilot_event_data(event).get("content")
    return [text] if isinstance(text, str) and text else []


def _copilot_mcp_policy_error(data: dict) -> tuple[str, str] | None:
    """A blocked required server makes the run unusable, even if the CLI continues."""
    message = data.get("message")
    if (data.get("warningType") != _WARNING_TYPE_MCP or not isinstance(message, str)
            or "blocked by policy" not in message.lower()):
        return None
    for server in ("findings", "quodeq-assistant"):
        if f"'{server}'" in message or f'"{server}"' in message:
            return (
                f"Copilot policy blocked Quodeq's required MCP server '{server}'. "
                "Ask your organization administrator to allow this MCP server. "
                "Signing in or selecting a model does not grant MCP access.",
                COPILOT_MCP_POLICY_REASON,
            )
    return None


def copilot_error(event: dict) -> tuple[str, str | None] | None:
    """Return a Copilot error message and optional non-retryable reason."""
    if event.get("type") == EVENT_TYPE_SESSION_WARNING:
        return _copilot_mcp_policy_error(copilot_event_data(event))
    if event.get("type") == EVENT_TYPE_SESSION_ERROR:
        data = copilot_event_data(event)
        message = data.get("message")
        category = data.get("errorType")
        reason = {"authentication": "auth", "authorization": "auth",
                  "quota": "quota", "policy": "policy"}.get(category) if isinstance(category, str) else None
        return (message if isinstance(message, str) and message else "Copilot session failed", reason)
    if event.get("type") == EVENT_TYPE_RESULT and event.get("exitCode"):
        return (f"Copilot exited with code {event['exitCode']}", None)
    return None


TEXT_EXTRACTORS: dict[str, Callable[[dict], list[str]]] = {
    EVENT_TYPE_ASSISTANT: texts_from_assistant,
    EVENT_TYPE_RESULT: texts_from_result,
    EVENT_TYPE_ITEM_COMPLETED: texts_from_item_completed,
    EVENT_TYPE_ASSISTANT_MESSAGE: texts_from_copilot,
}


def extract_files_from_blocks(blocks: list) -> set[str]:
    """Extract file paths from Read/Grep tool_use blocks."""
    files: set[str] = set()
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == _TOOL_USE_TYPE and block.get("name") in _FILE_READ_TOOLS:
            fp = (block.get("input") or {}).get("file_path") or (block.get("input") or {}).get("path")
            if fp:
                files.add(fp)
    return files


def parse_stream_event(line: str) -> dict | None:
    """Parse a single stream event line, returning None for empty or invalid lines."""
    stripped = line.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def extract_files_from_event(data: dict) -> set[str]:
    """Dispatch to the appropriate file extractor based on event type."""
    if not isinstance(data, dict):
        return set()
    etype = data.get("type", "")
    if etype == EVENT_TYPE_ASSISTANT:
        return extract_files_from_blocks(data.get("message", {}).get("content", []))
    if etype == EVENT_TYPE_ITEM_COMPLETED:
        return extract_files_from_blocks(data.get("item", {}).get("content", []))
    if etype == EVENT_TYPE_TOOL_EXECUTION_START:
        payload = copilot_event_data(data)
        args = payload.get("arguments")
        if payload.get("toolName") in _COPILOT_FILE_READ_TOOLS and isinstance(args, dict):
            path = args.get("path")
            if isinstance(path, str) and path:
                return {path}
    return set()
