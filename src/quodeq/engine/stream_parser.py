"""Stream-JSON event parser — extracts JSONL evidence lines from AI CLI output."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.engine._event_text import TEXT_EXTRACTORS
from quodeq.shared.logging import log_debug
from quodeq.shared.utils import TEXT_ENCODING

FINDING_TYPE_VIOLATION = "violation"
FINDING_TYPE_COMPLIANCE = "compliance"
_FINDING_TYPES = frozenset({FINDING_TYPE_VIOLATION, FINDING_TYPE_COMPLIANCE})


def _extract_jsonl_from_text(text: str, out) -> tuple[int, int]:
    """Scan text for JSONL evidence objects.

    Returns (evidence_count, total_lines_scanned).
    """
    count = 0
    lines = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lines += 1
        if line.startswith("```"):
            continue
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                if obj.get("p") and obj.get("t") in _FINDING_TYPES:
                    out.write(line + "\n")
                    count += 1
            except json.JSONDecodeError as exc:
                log_debug(f"Skipping malformed JSONL line: {exc}")
    return count, lines


def _extract_read_paths(blocks: list) -> set[str]:
    """Extract file paths from Read tool_use blocks in a content list."""
    files: set[str] = set()
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Read":
            fp = block.get("input", {}).get("file_path")
            if fp:
                files.add(fp)
    return files


def _collect_file_reads(data: dict) -> set[str]:
    """Extract file paths from Read tool_use blocks in an event."""
    files = _extract_read_paths(data.get("message", {}).get("content", []))
    files |= _extract_read_paths(data.get("item", {}).get("content", []))
    return files


def _process_texts(texts: list[str], out, stats: dict) -> None:
    """Write JSONL evidence from extracted text blocks, updating stats."""
    for raw_text in texts:
        stripped_text = raw_text.strip()
        if not stripped_text:
            continue
        stats["text_blocks"] += 1
        c, scanned = _extract_jsonl_from_text(stripped_text, out)
        stats["jsonl_lines"] += c
        stats["total_text_lines"] += scanned


def extract_evidence_from_stream(stream_file: Path, jsonl_file: Path) -> int:
    """Parse stream-json events and extract JSONL evidence lines.

    Args:
        stream_file: Path to the stream-json file from AI CLI.
        jsonl_file: Path to write extracted JSONL evidence.

    Returns:
        Number of unique files read by the AI during analysis.
    """
    stats: dict = {"text_blocks": 0, "jsonl_lines": 0, "total_text_lines": 0}
    files_read: set = set()

    with open(stream_file, encoding=TEXT_ENCODING) as f, open(jsonl_file, "w", encoding=TEXT_ENCODING) as out:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = data.get("type", "unknown")
            extractor = TEXT_EXTRACTORS.get(etype)
            if extractor:
                _process_texts(extractor(data), out, stats)
                files_read.update(_collect_file_reads(data))

    return len(files_read)
