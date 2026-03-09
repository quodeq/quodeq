"""Shared text extraction from stream-json events.

Used by both ``_fs_violations`` (dashboard live-view) and ``stream_parser``
(JSONL evidence extraction) to avoid duplicating the event-dispatch logic.
"""
from __future__ import annotations

from typing import Callable


def texts_from_assistant(event: dict) -> list[str]:
    """Extract text blocks from an ``assistant`` stream event."""
    texts: list[str] = []
    for block in (event.get("message") or {}).get("content") or []:
        if block.get("type") == "text" and block.get("text"):
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
    if item.get("type") == "agent_message":
        if item.get("text"):
            texts.append(item["text"])
        for block in item.get("content") or []:
            if block.get("type") in ("text", "output_text") and block.get("text"):
                texts.append(block["text"])
    return texts


TEXT_EXTRACTORS: dict[str, Callable[[dict], list[str]]] = {
    "assistant": texts_from_assistant,
    "result": texts_from_result,
    "item.completed": texts_from_item_completed,
}
