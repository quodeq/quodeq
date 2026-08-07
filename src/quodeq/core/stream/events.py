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
    if etype == "assistant":
        return extract_files_from_blocks(data.get("message", {}).get("content", []))
    if etype == "item.completed":
        return extract_files_from_blocks(data.get("item", {}).get("content", []))
    return set()
