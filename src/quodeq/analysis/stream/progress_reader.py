"""Incremental progress reader for AI analysis stream and JSONL files."""
from __future__ import annotations

import json as _json
from pathlib import Path

from quodeq.analysis.stream._incremental_lines import iter_line_batches
from quodeq.analysis.stream.counters import extract_files_from_event, parse_stream_event
from quodeq.shared.logging import log_debug

_TYPE_VIOLATION = "violation"
_TYPE_COMPLIANCE = "compliance"


class _IncrementalProgressReader:
    """Reads new bytes from stream/JSONL files since last check."""

    def __init__(self, stream_file: Path, jsonl_file: Path | None) -> None:
        self._stream_file = stream_file
        self._jsonl_file = jsonl_file
        self._stream_offset = 0
        self._jsonl_offset = 0
        self._seen_files: set[str] = set()
        self._jsonl_count = 0
        self._violations = 0
        self._compliances = 0

    def read_progress(self) -> dict:
        """Return incremental progress since the last call."""
        self._read_stream()
        self._read_jsonl()
        return {
            "files_read": len(self._seen_files),
            "evidence": self._jsonl_count,
            "violations": self._violations,
            "compliances": self._compliances,
        }

    def _read_stream(self) -> None:
        try:
            for lines, nbytes in iter_line_batches(self._stream_file, self._stream_offset):
                # Advance before processing this chunk's lines: on a
                # mid-batch error we still credit the chunk as consumed
                # (never re-read), but lose at most its own remainder.
                # Chunks not yet read stay unread for the next tick.
                self._stream_offset += nbytes
                self._consume_stream_lines(lines)
        except (OSError, ValueError) as exc:
            log_debug(f"Failed to read stream {self._stream_file}: {exc}")

    def _consume_stream_lines(self, lines: list[str]) -> None:
        for line in lines:
            data = parse_stream_event(line)
            if data is not None:
                self._seen_files.update(extract_files_from_event(data))

    def _read_jsonl(self) -> None:
        if self._jsonl_file is None or not self._jsonl_file.exists():
            return
        try:
            for lines, nbytes in iter_line_batches(self._jsonl_file, self._jsonl_offset):
                self._jsonl_offset += nbytes
                for line in lines:
                    self._count_evidence_line(line)
        except OSError as exc:
            log_debug(f"Failed to read JSONL {self._jsonl_file}: {exc}")

    def _count_evidence_line(self, line: str) -> None:
        stripped = line.strip()
        if not stripped:
            return
        self._jsonl_count += 1
        try:
            t = _json.loads(stripped).get("t", "")
        except (ValueError, AttributeError):
            t = ""
        if t == _TYPE_VIOLATION:
            self._violations += 1
        elif t == _TYPE_COMPLIANCE:
            self._compliances += 1
