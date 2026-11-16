"""Parse CLI stream-json lines into chat frames (text, tool-use and
tool-result details, session id)."""
from __future__ import annotations

import json
from quodeq.core.stream.agy_events import normalize_event
from quodeq.core.stream.events import (
    BLOCK_TYPE_OUTPUT_TEXT, BLOCK_TYPE_TEXT, BLOCK_TYPE_TOOL_USE, ITEM_TYPE_AGENT_MESSAGE,
    EVENT_TYPE_ASSISTANT, EVENT_TYPE_ASSISTANT_MESSAGE, EVENT_TYPE_ERROR, EVENT_TYPE_ITEM_COMPLETED,
    EVENT_TYPE_RESULT, EVENT_TYPE_TOOL_EXECUTION_START, EVENT_TYPE_TURN_FAILED,
    copilot_error, copilot_event_data, texts_from_copilot,
)

_TEXT_TYPES = (BLOCK_TYPE_TEXT, BLOCK_TYPE_OUTPUT_TEXT)

# Wire-format "type" values this dialect-agnostic parser branches on. Not in
# core/stream/events.py's EVENT_TYPE_* family: those are already-imported
# top-level event types, these are copilot/claude SSE-delta and codex
# sub-item types, each compared in exactly one place below.
_EVENT_TYPE_ASSISTANT_MESSAGE_DELTA = "assistant.message_delta"  # copilot delta wrapper
_EVENT_TYPE_STREAM_EVENT = "stream_event"  # claude/gemini --include-partial-messages wrapper
_EVENT_TYPE_ITEM_STARTED = "item.started"  # codex: a tool call begins
_EVENT_TYPE_SESSION_START = "session.start"  # copilot: session/thread id announced
_BLOCK_TYPE_CONTENT_BLOCK_DELTA = "content_block_delta"  # Anthropic SSE delta block type
_DELTA_TYPE_TEXT_DELTA = "text_delta"  # Anthropic SSE delta's own type
_ITEM_TYPE_MCP_TOOL_CALL = "mcp_tool_call"  # codex item type: an MCP tool invocation
_ITEM_TYPE_COMMAND_EXECUTION = "command_execution"  # codex item type: a shell command
_EVENT_TYPE_USER = "user"  # claude: the harness's turn, carrying tool results
_EVENT_TYPE_TOOL_EXECUTION_COMPLETE = "tool.execution_complete"  # copilot: a tool call finished
_BLOCK_TYPE_TOOL_RESULT = "tool_result"  # claude user-message content block type
_ITEM_STATUS_COMPLETED = "completed"  # codex item status when a tool call succeeded


def parse_line(line: str) -> dict | None:
    """One stream line as an event dict, or None if it is not a JSON object.

    Providers interleave non-JSON stderr chatter with the event stream, so a
    None here means "not an event", not "malformed event".
    """
    line = line.strip()
    if not line:
        return None
    try:
        obj = normalize_event(json.loads(line))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _texts_from_blocks(blocks) -> list[str]:
    out = []
    if isinstance(blocks, list):
        for b in blocks:
            if isinstance(b, dict) and b.get("type") in _TEXT_TYPES and isinstance(b.get("text"), str):
                out.append(b["text"])
    return out


def partial_text(event: dict) -> str | None:
    """Incremental text from a `stream_event` wrapper (claude/gemini
    --include-partial-messages): the Anthropic SSE `content_block_delta`
    carrying a `text_delta`. Thinking/tool-input deltas are not display text."""
    if event.get("type") == _EVENT_TYPE_ASSISTANT_MESSAGE_DELTA:
        text = copilot_event_data(event).get("deltaContent")
        return text if isinstance(text, str) else None
    if event.get("type") != _EVENT_TYPE_STREAM_EVENT:
        return None
    inner = event.get("event")
    if not isinstance(inner, dict) or inner.get("type") != _BLOCK_TYPE_CONTENT_BLOCK_DELTA:
        return None
    delta = inner.get("delta")
    if not isinstance(delta, dict) or delta.get("type") != _DELTA_TYPE_TEXT_DELTA:
        return None
    text = delta.get("text")
    return text if isinstance(text, str) else None


def _dict_field(container: object, key: str) -> object:
    """``container[key]`` when *container* is a dict, else None.

    The stream is untrusted JSON, so every nested lookup has to survive a
    non-dict at any level.
    """
    return container.get(key) if isinstance(container, dict) else None


def _message_blocks(event: dict) -> object:
    """The content blocks of an ``assistant`` event's message, or None."""
    return _dict_field(event.get("message"), "content")


def assistant_text(event: dict) -> list[str]:
    """The complete assistant text *event* carries, across the CLI dialects.

    claude sends `assistant` messages and a final `result`; codex sends
    `item.completed` agent_message items; copilot sends assistant messages
    of its own shape. Empty list for an event that carries no complete text
    (deltas go through ``partial_text``).
    """
    etype = event.get("type")
    if etype == EVENT_TYPE_ASSISTANT_MESSAGE:
        return texts_from_copilot(event)
    if etype == EVENT_TYPE_ASSISTANT:
        return _texts_from_blocks(_message_blocks(event))
    if etype == EVENT_TYPE_RESULT:
        result = event.get("result")
        return [result] if isinstance(result, str) else []
    if etype == EVENT_TYPE_ITEM_COMPLETED:
        item = event.get("item")
        item = item if isinstance(item, dict) else {}
        if item.get("type") == ITEM_TYPE_AGENT_MESSAGE:
            if isinstance(item.get("text"), str):
                return [item["text"]]
            return _texts_from_blocks(item.get("content"))
    return []


def _codex_tool_detail(item: dict) -> dict | None:
    """Map a codex `item` (mcp_tool_call / command_execution) to a tool-use detail."""
    itype = item.get("type")
    call_id = item.get("id") if isinstance(item.get("id"), str) else None
    if itype == _ITEM_TYPE_MCP_TOOL_CALL:
        name = item.get("tool")
        name = name if isinstance(name, str) and name else _ITEM_TYPE_MCP_TOOL_CALL
        return {"id": call_id, "name": name, "args": item.get("arguments")}
    if itype == _ITEM_TYPE_COMMAND_EXECUTION:
        cmd = item.get("command")
        return {"id": call_id, "name": "shell", "args": {"command": cmd} if isinstance(cmd, str) else None}
    return None


def tool_use_details(event: dict) -> list[dict]:
    """Tool calls *event* starts, as ``{id, name, args}``; ``id`` is None when
    the dialect announces none and ``args`` is the raw argument object.

    Claude carries tool calls as `tool_use` blocks inside `assistant`
    messages. Codex emits each tool call as its own `item.started` event;
    its `item.completed` is the matching result (see ``tool_result_details``).
    """
    etype = event.get("type")
    if etype == EVENT_TYPE_TOOL_EXECUTION_START:
        data = copilot_event_data(event)
        name = data.get("mcpToolName") or data.get("toolName")
        if isinstance(name, str) and name:
            call_id = data.get("toolCallId")
            return [{"id": call_id if isinstance(call_id, str) else None,
                     "name": name, "args": data.get("arguments")}]
        return []
    if etype == _EVENT_TYPE_ITEM_STARTED:
        item = event.get("item")
        detail = _codex_tool_detail(item) if isinstance(item, dict) else None
        return [detail] if detail else []
    blocks = _message_blocks(event) if etype == EVENT_TYPE_ASSISTANT else None
    details = []
    if isinstance(blocks, list):
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == BLOCK_TYPE_TOOL_USE and isinstance(b.get("name"), str):
                call_id = b.get("id")
                details.append({"id": call_id if isinstance(call_id, str) else None,
                                "name": b["name"], "args": b.get("input")})
    return details


def tool_uses(event: dict) -> list[str]:
    """Just the tool names from *event*, for callers that skip the details."""
    return [d["name"] for d in tool_use_details(event)]


def tool_result_details(event: dict) -> list[dict]:
    """Tool calls *event* finishes, as ``{id, name, ok}``.

    Claude returns results as `tool_result` blocks in a `user` message, keyed
    by `tool_use_id` (so ``name`` is None). Codex closes a tool item with
    `item.completed` and copilot with `tool.execution_complete`, each keyed
    by its call id when it has one, else by tool name.
    """
    etype = event.get("type")
    if etype == _EVENT_TYPE_TOOL_EXECUTION_COMPLETE:
        data = copilot_event_data(event)
        name = data.get("mcpToolName") or data.get("toolName")
        call_id = data.get("toolCallId")
        return [{"id": call_id if isinstance(call_id, str) else None,
                 "name": name if isinstance(name, str) else None,
                 "ok": not data.get("error") and data.get("success") is not False}]
    if etype == _EVENT_TYPE_USER:
        blocks = _message_blocks(event)
        out = []
        if isinstance(blocks, list):
            for b in blocks:
                if isinstance(b, dict) and b.get("type") == _BLOCK_TYPE_TOOL_RESULT and isinstance(b.get("tool_use_id"), str):
                    out.append({"id": b["tool_use_id"], "name": None, "ok": not b.get("is_error", False)})
        return out
    if etype == EVENT_TYPE_ITEM_COMPLETED:
        item = event.get("item")
        detail = _codex_tool_detail(item) if isinstance(item, dict) else None
        if detail is None:
            return []
        ok = item.get("status") == _ITEM_STATUS_COMPLETED and not item.get("error")
        if item.get("type") == _ITEM_TYPE_COMMAND_EXECUTION:
            ok = item.get("exit_code") in (0, None) and ok
        return [{"id": detail["id"], "name": detail["name"], "ok": ok}]
    return []


def _nested_error_message(value) -> str | None:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value if value else None
        return _nested_error_message(parsed) or value
    if not isinstance(value, dict):
        return None
    err = value.get("error")
    if isinstance(err, dict) and isinstance(err.get("message"), str):
        return err["message"]
    msg = value.get("message")
    return msg if isinstance(msg, str) and msg else None


def error_message(event: dict) -> str | None:
    """The message of a structured failure event, or None for a normal event.

    Covers copilot's error events, claude's `error` and codex's
    `turn.failed`, unwrapping the JSON-in-a-string form each can use.
    """
    error = copilot_error(event)
    if error:
        return error[0]
    if event.get("type") == EVENT_TYPE_ERROR:
        return _nested_error_message(event.get("message")) or _nested_error_message(event)
    if event.get("type") == EVENT_TYPE_TURN_FAILED:
        return _nested_error_message(event.get("error")) or _nested_error_message(event)
    return None


def session_id(event: dict) -> str | None:
    """The CLI session/thread id *event* announces, under any dialect's spelling."""
    sid = event.get("session_id") or event.get("thread_id") or event.get("sessionId")
    if not sid and event.get("type") == _EVENT_TYPE_SESSION_START:
        sid = copilot_event_data(event).get("sessionId")
    return sid if isinstance(sid, str) else None
