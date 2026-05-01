"""Thread-safe ring buffer for capturing log lines."""
from __future__ import annotations

import logging
import re
import threading
from collections import deque
from datetime import datetime, timezone

_DEFAULT_MAX_LINES = 500

# Werkzeug's default access-log format. Each request is logged twice in
# the buffer: once as `quodeq.api` ("API: GET …") at request entry, and
# once by Werkzeug at response. The Werkzeug copy is the one the user
# sees as duplication — drop the 2xx/3xx ones, keep 4xx/5xx because a
# failed request is the actionable signal.
_WERKZEUG_ACCESS_RE = re.compile(r'"\w+ \S+ HTTP/[\d.]+" (\d+)')

# Endpoints the dashboard polls continuously. Each successful poll adds
# zero information to the log — only failures are interesting. Drop both
# the `API: …` entry-log line AND the Werkzeug access line for these
# paths when status is 2xx/3xx; failures still surface via the Werkzeug
# 4xx/5xx branch in `_is_noisy_werkzeug_access`.
_NOISY_POLL_PATHS = (
    "/api/health",
    "/api/logs",
    "/api/ollama/status",
)
_API_ENTRY_PATH_RE = re.compile(r"^API: \S+ (\S+)")
_WERKZEUG_PATH_RE = re.compile(r'"\S+ (\S+) HTTP/')


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


def _path_no_query(path: str) -> str:
    return path.split("?", 1)[0]


def _is_noisy_werkzeug_access(record: logging.LogRecord) -> bool:
    if record.name != "werkzeug":
        return False
    m = _WERKZEUG_ACCESS_RE.search(record.getMessage())
    if not m:
        return False
    try:
        status = int(m.group(1))
    except ValueError:
        return False
    return 200 <= status < 400


def _is_noisy_poll(record: logging.LogRecord) -> bool:
    msg = record.getMessage()
    if record.name == "quodeq.api":
        m = _API_ENTRY_PATH_RE.match(msg)
        if m and _path_no_query(m.group(1)) in _NOISY_POLL_PATHS:
            return True
    if record.name == "werkzeug":
        m = _WERKZEUG_PATH_RE.search(msg)
        if not m:
            return False
        if _path_no_query(m.group(1)) not in _NOISY_POLL_PATHS:
            return False
        status_m = _WERKZEUG_ACCESS_RE.search(msg)
        if not status_m:
            return False
        try:
            status = int(status_m.group(1))
        except ValueError:
            return False
        return 200 <= status < 400
    return False


class _BufferHandler(logging.Handler):
    """Logging handler that writes formatted records into a LogBuffer."""

    def __init__(self, buffer: LogBuffer) -> None:
        super().__init__()
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        if _is_noisy_poll(record):
            return
        if _is_noisy_werkzeug_access(record):
            return
        self._buffer.append(self.format(record))
