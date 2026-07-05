"""Parse CLI stream-json lines into chat frames (text, tool-use, session id)."""
from __future__ import annotations

import json

_TEXT_TYPES = ("text", "output_text")


def parse_line(line: str) -> dict | None:
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


def assistant_text(event: dict) -> list[str]:
    etype = event.get("type")
    if etype == "assistant":
        msg = event.get("message")
        blocks = msg.get("content") if isinstance(msg, dict) else None
        return _texts_from_blocks(blocks)
    if etype == "result":
        result = event.get("result")
        return [result] if isinstance(result, str) else []
    if etype == "item.completed":
        item = event.get("item")
        item = item if isinstance(item, dict) else {}
        if item.get("type") == "agent_message":
            if isinstance(item.get("text"), str):
                return [item["text"]]
            return _texts_from_blocks(item.get("content"))
    return []


def tool_use_details(event: dict) -> list[dict]:
    """tool_use blocks as {name, args_summary}; args JSON truncated for display."""
    if event.get("type") == "assistant":
        msg = event.get("message")
        blocks = msg.get("content") if isinstance(msg, dict) else None
    elif event.get("type") == "item.completed":
        item = event.get("item")
        blocks = item.get("content") if isinstance(item, dict) else None
    else:
        blocks = None
    details = []
    if isinstance(blocks, list):
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "tool_use" and isinstance(b.get("name"), str):
                args = b.get("input")
                summary = (json.dumps(args, ensure_ascii=False)[:80]
                           if isinstance(args, dict) and args else "")
                details.append({"name": b["name"], "args_summary": summary})
    return details


def tool_uses(event: dict) -> list[str]:
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
    if event.get("type") == "error":
        return _nested_error_message(event.get("message")) or _nested_error_message(event)
    if event.get("type") == "turn.failed":
        return _nested_error_message(event.get("error")) or _nested_error_message(event)
    return None


def session_id(event: dict) -> str | None:
    sid = event.get("session_id") or event.get("thread_id")
    return sid if isinstance(sid, str) else None
