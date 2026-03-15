"""Incremental progress reader for AI analysis stream and JSONL files."""
from __future__ import annotations

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

    def read_progress(self) -> dict:
        """Return incremental progress since the last call."""
        self._read_stream()
        self._read_jsonl()
        return {"files_read": len(self._seen_files), "evidence": self._jsonl_count}

    def _read_stream(self) -> None:
        try:
            with open(self._stream_file, "rb") as f:
                f.seek(self._stream_offset)
                new_bytes = f.read()
                self._stream_offset += len(new_bytes)
            for line in new_bytes.decode("utf-8", errors="replace").splitlines():
                data = parse_stream_event(line)
                if data is not None:
                    self._seen_files.update(extract_files_from_event(data))
        except (OSError, ValueError) as exc:
            log_debug(f"Failed to read stream {self._stream_file}: {exc}")

    def _read_jsonl(self) -> None:
        if self._jsonl_file is None or not self._jsonl_file.exists():
            return
        try:
            with open(self._jsonl_file, "rb") as jf:
                jf.seek(self._jsonl_offset)
                new_bytes = jf.read()
                self._jsonl_offset += len(new_bytes)
            self._jsonl_count += sum(
                1 for line in new_bytes.decode("utf-8", errors="replace").splitlines()
                if line.strip()
            )
        except OSError as exc:
            log_debug(f"Failed to read JSONL {self._jsonl_file}: {exc}")
