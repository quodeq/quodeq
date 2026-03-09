"""Stream-JSON event parser — extracts JSONL evidence lines from AI CLI output."""
from __future__ import annotations

import json
from pathlib import Path


def _extract_jsonl_from_text(text: str, out) -> tuple[int, int]:
    """Scan text for JSONL evidence objects.

    Returns (evidence_count, total_lines_scanned).
    """
    count = 0
    lines = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        lines += 1
        if line.startswith("```"):
            continue
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                if obj.get("p") and obj.get("t") in ("violation", "compliance"):
                    out.write(line + "\n")
                    count += 1
            except json.JSONDecodeError:
                pass
    return count, lines


def _process_assistant_event(data: dict, out, stats: dict, files_read: set) -> None:
    msg = data.get("message", {})
    for block in msg.get("content", []):
        btype = block.get("type")
        if btype == "text":
            text = block["text"].strip()
            if text:
                stats["text_blocks"] += 1
                c, scanned = _extract_jsonl_from_text(text, out)
                stats["jsonl_lines"] += c
                stats["total_text_lines"] += scanned
        elif btype == "tool_use" and block.get("name") == "Read":
            fp = block.get("input", {}).get("file_path")
            if fp:
                files_read.add(fp)


def _process_result_event(data: dict, out, stats: dict) -> None:
    result = data.get("result", "").strip()
    if result:
        stats["text_blocks"] += 1
        c, scanned = _extract_jsonl_from_text(result, out)
        stats["jsonl_lines"] += c
        stats["total_text_lines"] += scanned


def _extract_from_content_blocks(blocks: list, out, stats: dict, files_read: set) -> None:
    """Process content blocks from an item.completed event, extracting text and file reads."""
    for block in blocks:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype in ("text", "output_text"):
            block_text = (block.get("text") or "").strip()
            if block_text:
                stats["text_blocks"] += 1
                c, scanned = _extract_jsonl_from_text(block_text, out)
                stats["jsonl_lines"] += c
                stats["total_text_lines"] += scanned
        elif btype == "tool_use" and block.get("name") == "Read":
            fp = block.get("input", {}).get("file_path")
            if fp:
                files_read.add(fp)


def _process_item_completed_event(data: dict, out, stats: dict, files_read: set) -> None:
    item = data.get("item", {})
    if item.get("type") == "agent_message":
        text = (item.get("text") or "").strip()
        if text:
            stats["text_blocks"] += 1
            c, scanned = _extract_jsonl_from_text(text, out)
            stats["jsonl_lines"] += c
            stats["total_text_lines"] += scanned
        _extract_from_content_blocks(item.get("content", []), out, stats, files_read)


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

    with open(stream_file) as f, open(jsonl_file, "w") as out:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = data.get("type", "unknown")

            if etype == "assistant":
                _process_assistant_event(data, out, stats, files_read)
            elif etype == "result":
                _process_result_event(data, out, stats)
            elif etype == "item.completed":
                _process_item_completed_event(data, out, stats, files_read)

    return len(files_read)
