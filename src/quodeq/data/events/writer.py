"""Append-only JSONL writer for the run event log."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from quodeq.core.events.models import BaseEvent
from quodeq.data.events.codec import event_to_json
from quodeq.data.locking import get_file_lock


_logger = logging.getLogger(__name__)


class EventLogWriter:
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

    def _ensure_dir(self) -> None:
        """Ensures the parent directory of the log file exists."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: BaseEvent) -> None:
        """Append one event to the JSONL log. Raises if the write fails; nothing is buffered."""
        self._append([event], f"event {event.event_id}")

    def emit_many(self, events: Iterable[BaseEvent]) -> None:
        """Append every event under one open, one lock and one flush.

        The batch is serialized before the log is opened, so a bad event
        leaves the file untouched. An empty batch opens nothing.
        """
        batch = list(events)
        if batch:
            self._append(batch, f"{len(batch)} events")

    def _append(self, events: list[BaseEvent], what: str) -> None:
        try:
            lines = [event_to_json(event) + "\n" for event in events]
            with open(self.log_path, mode="a", encoding="utf-8") as f:
                self._lock.acquire(f)
                try:
                    f.writelines(lines)
                    f.flush()
                finally:
                    self._lock.release(f)
        except Exception as e:
            _logger.error("Failed to emit %s to %s: %s", what, self.log_path, e)
            raise

    def __repr__(self) -> str:
        return f"<EventLogWriter(path={self.log_path})>"
