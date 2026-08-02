"""Counting reads over agent stream/JSONL output files.

The parsing itself is pure and lives in ``core/stream/events.py``; these
helpers add the file access, so both the analysis pipeline and the
services layer can reach them without a services -> analysis arrow.
Both degrade to an empty result on unreadable files: they feed progress
counters, never correctness.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.stream.events import extract_files_from_event, parse_stream_event
from quodeq.shared.logging import log_debug
from quodeq.shared.utils import open_text


def count_files_in_stream(stream_file: Path) -> set[str]:
    """Extract unique file paths from Read/Grep tool_use events in the stream."""
    files: set[str] = set()
    try:
        with open_text(stream_file) as f:
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
        with open_text(jsonl_file) as f:
            return sum(1 for line in f if line.strip())
    except OSError as exc:
        log_debug(f"Failed to count JSONL lines from {jsonl_file}: {exc}")
        return 0
