"""Complete lines appended to a growing file since the previous read.

Agents append to evidence and findings JSONL while a pool runs, so a poll
only needs the bytes written since the last one. The consumed tail is
remembered; when the file is shorter than the offset or the tail no longer
matches (the end-of-pool dedup pass rewrites the file in place), reading
restarts from zero.
"""
from __future__ import annotations

import logging
from pathlib import Path

_logger = logging.getLogger(__name__)

_TAIL_GUARD = 512  # bytes of the consumed tail re-checked to detect a rewrite


class AppendedLines:
    """Complete lines appended to *path* since the previous ``read``."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.offset = 0
        self._tail = b""

    def read(self) -> tuple[bool, list[str]]:
        """``(restarted, lines)``: *restarted* when the file was rewritten and
        *lines* start from its beginning again. A trailing partial line (an
        agent mid-write) waits for the next call."""
        restarted = False
        try:
            with open(self.path, "rb") as f:
                size = f.seek(0, 2)
                if size < self.offset or not self._tail_matches(f):
                    self.offset, self._tail, restarted = 0, b"", True
                f.seek(self.offset)
                data = f.read()
        except OSError as exc:
            _logger.debug("appended-lines file unreadable: %s", exc)
            return (False, [])
        end = data.rfind(b"\n")
        if end < 0:
            return (restarted, [])
        complete = data[: end + 1]
        self.offset += len(complete)
        self._tail = complete[-_TAIL_GUARD:]
        return (restarted, complete.decode("utf-8", errors="replace").splitlines())

    def _tail_matches(self, f) -> bool:
        if not self._tail:
            return True
        f.seek(self.offset - len(self._tail))
        return f.read(len(self._tail)) == self._tail
