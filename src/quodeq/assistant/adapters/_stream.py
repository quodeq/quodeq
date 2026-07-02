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
        return _texts_from_blocks(event.get("message", {}).get("content"))
    if etype == "result":
        result = event.get("result")
        return [result] if isinstance(result, str) else []
    if etype == "item.completed":
        item = event.get("item", {})
        if item.get("type") == "agent_message":
            if isinstance(item.get("text"), str):
                return [item["text"]]
            return _texts_from_blocks(item.get("content"))
    return []


def tool_uses(event: dict) -> list[str]:
    if event.get("type") == "assistant":
        blocks = event.get("message", {}).get("content")
    elif event.get("type") == "item.completed":
        blocks = event.get("item", {}).get("content")
    else:
        blocks = None
    names = []
    if isinstance(blocks, list):
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "tool_use" and isinstance(b.get("name"), str):
                names.append(b["name"])
    return names


def session_id(event: dict) -> str | None:
    sid = event.get("session_id") or event.get("thread_id")
    return sid if isinstance(sid, str) else None
