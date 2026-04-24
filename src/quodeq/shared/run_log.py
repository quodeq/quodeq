"""Per-run log file writer.

Appends the evaluation's stderr-stream verbatim to ``{run_dir}/run.log``.
Used by both the CLI pipeline and the dashboard subprocess dispatcher.

Failures are silent-by-design: this file is diagnostic, never load-bearing.
A disk-full or permission error must not abort an evaluation.
"""
from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import IO

_LOG_FILENAME = "run.log"


class RunLogWriter:
    """Thread-safe append-only writer for a per-run log file."""

    def __init__(self, run_dir: Path) -> None:
        self._path = run_dir / _LOG_FILENAME
        self._fh: IO[str] | None = None
        self._lock = threading.Lock()
        self._disabled = False
        try:
            self._fh = open(self._path, "a", buffering=1, encoding="utf-8")
        except OSError as exc:
            print(f"run_log: could not open {self._path}: {exc}", file=sys.stderr)
            self._disabled = True

    @property
    def path(self) -> Path:
        return self._path

    def write(self, line: str) -> None:
        """Append *line* to run.log. Adds a trailing newline if missing.

        Safe under concurrent close(): the ``_fh is None`` check lives INSIDE
        the lock, so a close() that races with this call cannot leave us
        calling ``None.write(...)``.
        """
        if self._disabled:
            return
        text = line if line.endswith("\n") else line + "\n"
        with self._lock:
            fh = self._fh
            if fh is None:
                return  # closed (serially or concurrently) — silently drop
            try:
                fh.write(text)
                fh.flush()
            except OSError:
                self._disabled = True

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.close()
                finally:
                    self._fh = None

    # Context-manager protocol — lets callers write `with RunLogWriter(d) as w:`
    # for guaranteed cleanup on any exit path.
    def __enter__(self) -> "RunLogWriter":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


class RunLogHandler(logging.Handler):
    """logging.Handler that forwards formatted records to a RunLogWriter."""

    def __init__(self, writer: RunLogWriter) -> None:
        super().__init__()
        self._writer = writer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._writer.write(self.format(record))
        except Exception:
            # Logging must never crash the app.
            pass
