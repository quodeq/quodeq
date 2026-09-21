"""Parse CLI stream-json lines into chat frames (text, tool-use, session id)."""
from __future__ import annotations

import json
from quodeq.core.stream.events import (
    EVENT_TYPE_ASSISTANT, EVENT_TYPE_ASSISTANT_MESSAGE, EVENT_TYPE_ITEM_COMPLETED,
    EVENT_TYPE_RESULT, EVENT_TYPE_TOOL_EXECUTION_START,
    copilot_error, copilot_event_data, texts_from_copilot,
)

_TEXT_TYPES = ("text", "output_text")
_ARGS_SUMMARY_MAX_CHARS = 80  # display truncation width for a tool call's args/command summary


def parse_line(line: str) -> dict | None:
    """One stream line as an event dict, or None if it is not a JSON object.

    Providers interleave non-JSON stderr chatter with the event stream, so a
    None here means "not an event", not "malformed event".
    """
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
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
    if event.get("type") == "assistant.message_delta":
        text = copilot_event_data(event).get("deltaContent")
        return text if isinstance(text, str) else None
    if event.get("type") != "stream_event":
        return None
    inner = event.get("event")
    if not isinstance(inner, dict) or inner.get("type") != "content_block_delta":
        return None
    delta = inner.get("delta")
    if not isinstance(delta, dict) or delta.get("type") != "text_delta":
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
        if item.get("type") == "agent_message":
            if isinstance(item.get("text"), str):
                return [item["text"]]
            return _texts_from_blocks(item.get("content"))
    return []


def _args_summary(args) -> str:
    return (json.dumps(args, ensure_ascii=False)[:_ARGS_SUMMARY_MAX_CHARS]
            if isinstance(args, dict) and args else "")


def _codex_tool_detail(item: dict) -> dict | None:
    """Map a codex `item` (mcp_tool_call / command_execution) to a tool frame."""
    itype = item.get("type")
    if itype == "mcp_tool_call":
        name = item.get("tool")
        name = name if isinstance(name, str) and name else "mcp_tool_call"
        return {"name": name, "args_summary": _args_summary(item.get("arguments"))}
    if itype == "command_execution":
        cmd = item.get("command")
        return {"name": "shell", "args_summary": cmd[:_ARGS_SUMMARY_MAX_CHARS] if isinstance(cmd, str) else ""}
    return None


def tool_use_details(event: dict) -> list[dict]:
    """tool_use blocks as {name, args_summary}; args JSON truncated for display.

    Claude carries tool calls as `tool_use` blocks inside `assistant` messages.
    Codex emits each tool call as its own event: `item.started` when the call
    begins (surfaced here, once) and `item.completed` when it finishes (ignored
    to avoid a duplicate frame).
    """
    etype = event.get("type")
    if etype == EVENT_TYPE_TOOL_EXECUTION_START:
        data = copilot_event_data(event)
        name = data.get("mcpToolName") or data.get("toolName")
        if isinstance(name, str) and name:
            return [{"name": name, "args_summary": _args_summary(data.get("arguments"))}]
        return []
    if etype == "item.started":
        item = event.get("item")
        detail = _codex_tool_detail(item) if isinstance(item, dict) else None
        return [detail] if detail else []
    if etype == EVENT_TYPE_ASSISTANT:
        blocks = _message_blocks(event)
    elif etype == EVENT_TYPE_ITEM_COMPLETED:
        blocks = _dict_field(event.get("item"), "content")
    else:
        blocks = None
    details = []
    if isinstance(blocks, list):
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "tool_use" and isinstance(b.get("name"), str):
                details.append({"name": b["name"], "args_summary": _args_summary(b.get("input"))})
    return details


def tool_uses(event: dict) -> list[str]:
    """Just the tool names from *event*, for callers that skip the args summary."""
    return [d["name"] for d in tool_use_details(event)]


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
    if event.get("type") == "error":
        return _nested_error_message(event.get("message")) or _nested_error_message(event)
    if event.get("type") == "turn.failed":
        return _nested_error_message(event.get("error")) or _nested_error_message(event)
    return None


def session_id(event: dict) -> str | None:
    """The CLI session/thread id *event* announces, under any dialect's spelling."""
    sid = event.get("session_id") or event.get("thread_id") or event.get("sessionId")
    if not sid and event.get("type") == "session.start":
        sid = copilot_event_data(event).get("sessionId")
    return sid if isinstance(sid, str) else None
