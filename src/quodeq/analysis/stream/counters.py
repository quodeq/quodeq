"""Stream and JSONL file counting helpers for AI analysis output."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.shared.logging import log_debug
from quodeq.shared.utils import TEXT_ENCODING

_TOOL_USE_TYPE = "tool_use"
_FILE_READ_TOOLS = frozenset({"Read", "Grep"})


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
    etype = data.get("type", "")
    if etype == "assistant":
        return extract_files_from_blocks(data.get("message", {}).get("content", []))
    if etype == "item.completed":
        return extract_files_from_blocks(data.get("item", {}).get("content", []))
    return set()


def count_files_in_stream(stream_file: Path) -> set[str]:
    """Extract unique file paths from Read/Grep tool_use events in the stream."""
    files: set[str] = set()
    try:
        with open(stream_file, encoding=TEXT_ENCODING) as f:
            for line in f:
                data = parse_stream_event(line)
                if data is not None:
                    files.update(extract_files_from_event(data))
    except (OSError, ValueError) as exc:
        log_debug(f"Failed to count files from stream {stream_file}: {exc}")
    return files


def count_jsonl_lines(jsonl_file: Path) -> int:
    """Count evidence lines in the JSONL file written by the MCP server."""
    try:
        if not jsonl_file.exists():
            return 0
        with open(jsonl_file, encoding=TEXT_ENCODING) as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0
