"""Incremental reader over one dispatch's evidence JSONL.

``persist_dispatch_results`` runs on every periodic-persist tick for the
life of a dispatch (``_persist_watcher.py``). Re-reading and re-parsing the
whole JSONL each tick made persist cost grow with elapsed dispatch time.
``DispatchJsonlState`` keeps the parsed view between ticks and consumes only
the bytes appended since the previous call.

The byte offset is trusted only while the bytes just before it are still
the ones consumed last (the trailing ``_GUARD_BYTES`` of the prefix). Two
things move them: truncation, and the pool's in-place ``deduplicate_jsonl``
rewrite at the end of a dispatch, which can drop lines *before* the offset
while a longer tail keeps the file at least as large as before, so a size
check alone would seek into the middle of a line. Either trips the guard
and forces a re-read from byte 0. That re-read marks every file dirty
again, so the next persist rewrites all of them, exactly as a full read did.

One state belongs to one watcher thread; it is not synchronised.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

# Trailing bytes of the consumed prefix kept for the rewrite guard. Longer
# than any realistic run of repeated bytes in a findings JSONL, so a shifted
# rewrite cannot line up with it by accident.
_GUARD_BYTES = 512


@dataclass
class DispatchJsonlState:
    """Parsed view of a dispatch JSONL and the byte offset it covers.

    ``grouped`` maps file -> findings (marker lines excluded), ``last_status``
    maps file -> its most recent file_done status, ``dirty`` holds the files
    touched since the caller last cleared it (after a persist).
    """

    offset: int = 0
    grouped: dict[str, list[dict]] = field(default_factory=dict)
    last_status: dict[str, str] = field(default_factory=dict)
    dirty: set[str] = field(default_factory=set)
    _guard: bytes = field(default=b"", repr=False)

    def ok_files(self) -> set[str]:
        """Files whose most recent file_done marker has status='ok'."""
        return {f for f, s in self.last_status.items() if s == "ok"}

    def reset(self) -> None:
        self.offset = 0
        self._guard = b""
        self.grouped.clear()
        self.last_status.clear()
        self.dirty.clear()

    def advance(self, jsonl_path: Path, *, include_tail: bool = False) -> None:
        """Consume the lines appended since the previous call.

        Only newline-terminated lines are consumed; a torn trailing line is
        left for the writer to finish, unless *include_tail* asks for a
        one-shot read of a finished file. A missing file reads as empty. An
        unreadable one raises OSError for the caller to log (this module
        keeps no logger, see tests/tools/test_logging_boundary.py); the next
        call resumes from the last consistent offset.
        """
        if not jsonl_path.is_file():
            self.reset()
            return
        with jsonl_path.open("rb") as fh:
            if not self._prefix_intact(fh):
                self.reset()
            fh.seek(self.offset)
            data = fh.read()
        end = len(data) if include_tail else data.rfind(b"\n") + 1
        if end == 0:
            return
        self.offset += end
        self._guard = (self._guard + data[:end])[-_GUARD_BYTES:]
        for raw in data[:end].split(b"\n"):
            self._ingest(raw.strip())

    def _prefix_intact(self, fh: BinaryIO) -> bool:
        """True while the bytes before ``offset`` are the ones consumed last."""
        if self.offset == 0:
            return True
        fh.seek(self.offset - len(self._guard))
        return fh.read(len(self._guard)) == self._guard

    def _ingest(self, raw: bytes) -> None:
        if not raw:
            return
        try:
            entry = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(entry, dict):
            return
        f = entry.get("file")
        if not isinstance(f, str):
            return
        if entry.get("_marker") == "file_done":
            if entry.get("status") in ("ok", "error"):
                self.last_status[f] = entry["status"]
                self.dirty.add(f)
        elif f:
            self.grouped.setdefault(f, []).append(entry)
            self.dirty.add(f)
