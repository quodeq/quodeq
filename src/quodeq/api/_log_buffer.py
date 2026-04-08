"""Thread-safe ring buffer for capturing log lines."""
from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timezone

_DEFAULT_MAX_LINES = 500


class LogBuffer:
    """Fixed-size ring buffer that stores log lines with monotonic indices.

    Usage::

        buf = LogBuffer(max_lines=500)
        logging.getLogger("werkzeug").addHandler(buf.handler)
        # later
        result = buf.get_lines(since=last_index)
    """

    def __init__(self, max_lines: int = _DEFAULT_MAX_LINES) -> None:
        self._max = max_lines
        self._entries: deque[dict] = deque(maxlen=max_lines)
        self._index = 0
        self._lock = threading.Lock()
        self._handler = _BufferHandler(self)
        self._handler.setFormatter(logging.Formatter("%(message)s"))

    @property
    def handler(self) -> logging.Handler:
        """Return a logging.Handler that feeds into this buffer."""
        return self._handler

    def append(self, line: str) -> None:
        """Add a log line to the buffer."""
        with self._lock:
            self._entries.append({
                "index": self._index,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "line": line,
            })
            self._index += 1

    def get_lines(self, since: int | None = None) -> dict:
        """Return buffered lines, optionally filtered by index.

        Args:
            since: If provided, return only entries with index > since.

        Returns:
            ``{"lines": [...], "total": int}``
        """
        with self._lock:
            if since is not None:
                lines = [e for e in self._entries if e["index"] > since]
            else:
                lines = list(self._entries)
            return {"lines": lines, "total": self._index}

    def clear(self) -> None:
        """Remove all buffered entries and reset the index."""
        with self._lock:
            self._entries.clear()
            self._index = 0


class _BufferHandler(logging.Handler):
    """Logging handler that writes formatted records into a LogBuffer."""

    def __init__(self, buffer: LogBuffer) -> None:
        super().__init__()
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        self._buffer.append(self.format(record))
