"""Append-only JSONL writer for the run event log."""
from __future__ import annotations

import logging
from pathlib import Path

from quodeq.core.events.models import BaseEvent
from quodeq.data.jsonl_append import JsonlAppendMixin
from quodeq.data.locking import get_file_lock


_logger = logging.getLogger(__name__)


class EventLogWriter(JsonlAppendMixin):
    """Thread-safe, append-only writer for the Quodeq Event Log (JSONL).

    Data-layer adapter: the sole writer of ``events.jsonl``, the immutable
    source of truth. The event TYPES it serializes are core
    (``core/events/models.py``); the file mechanics (locking, append, flush)
    live here in ``data/events/``.
    """

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self._ensure_dir()
        self._lock = get_file_lock()
        self._logger = _logger

    def _ensure_dir(self) -> None:
        """Ensures the parent directory of the log file exists."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _emit_what(self, event: BaseEvent) -> str:
        return f"event {event.event_id}"

    def __repr__(self) -> str:
        return f"<EventLogWriter(path={self.log_path})>"
