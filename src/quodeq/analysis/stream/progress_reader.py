"""Incremental progress reader for AI analysis stream and JSONL files."""
from __future__ import annotations

import json as _json
from pathlib import Path

from quodeq.analysis.stream.counters import extract_files_from_event, parse_stream_event
from quodeq.shared.logging import log_debug


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

    _READ_CHUNK = 1 << 16  # 64 KiB

    def _read_stream(self) -> None:
        try:
            partial = ""
            with open(self._stream_file, "rb") as f:
                f.seek(self._stream_offset)
                while True:
                    chunk = f.read(self._READ_CHUNK)
                    if not chunk:
                        break
                    self._stream_offset += len(chunk)
                    text = partial + chunk.decode("utf-8", errors="replace")
                    lines = text.split("\n")
                    # Last element may be incomplete — save for next chunk
                    partial = lines.pop()
                    for line in lines:
                        data = parse_stream_event(line)
                        if data is not None:
                            self._seen_files.update(extract_files_from_event(data))
            # Process any remaining partial line
            if partial.strip():
                data = parse_stream_event(partial)
                if data is not None:
                    self._seen_files.update(extract_files_from_event(data))
        except (OSError, ValueError) as exc:
            log_debug(f"Failed to read stream {self._stream_file}: {exc}")

    def _read_jsonl(self) -> None:
        if self._jsonl_file is None or not self._jsonl_file.exists():
            return
        try:
            partial = ""
            with open(self._jsonl_file, "rb") as jf:
                jf.seek(self._jsonl_offset)
                while True:
                    chunk = jf.read(self._READ_CHUNK)
                    if not chunk:
                        break
                    self._jsonl_offset += len(chunk)
                    text = partial + chunk.decode("utf-8", errors="replace")
                    lines = text.split("\n")
                    partial = lines.pop()
                    for line in lines:
                        stripped = line.strip()
                        if not stripped:
                            continue
                        self._jsonl_count += 1
                        try:
                            t = _json.loads(stripped).get("t", "")
                        except (ValueError, AttributeError):
                            t = ""
                        if t == "violation":
                            self._violations += 1
                        elif t == "compliance":
                            self._compliances += 1
            if partial.strip():
                self._jsonl_count += 1
                try:
                    t = _json.loads(partial.strip()).get("t", "")
                except (ValueError, AttributeError):
                    t = ""
                if t == "violation":
                    self._violations += 1
                elif t == "compliance":
                    self._compliances += 1
        except OSError as exc:
            log_debug(f"Failed to read JSONL {self._jsonl_file}: {exc}")
