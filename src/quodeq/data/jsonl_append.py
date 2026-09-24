"""Shared batched-append mechanics for the JSONL action and event logs.

Both ``ActionLogWriter`` (``data/actions_log.py``) and ``EventLogWriter``
(``data/events/writer.py``) append a batch of events the same way: serialize
everything first, then one open, one file lock, one ``writelines``, one
flush, log-then-raise on failure.

Not given a leading underscore: ``data/events`` is a different directory
from ``data``, and a private module can only be imported from files in the
directory that owns it (see tools/check_private_imports.py, rule B). This
mirrors ``data/locking.py``, the other helper both writers already share.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from quodeq.core.events.models import BaseEvent
from quodeq.data.events.codec import event_to_json
from quodeq.data.locking import FileLock


def append_jsonl_batch(
    log_path: Path,
    events: list[BaseEvent],
    *,
    lock: FileLock,
    logger: logging.Logger,
    what: str,
) -> None:
    """Serialize every event, then append them all under one open+lock+flush.

    Serialization happens before the log is opened, so a bad event leaves
    the file untouched. On any failure, logs ``what`` and ``log_path`` at
    ERROR and re-raises; nothing is swallowed.
    """
    try:
        lines = [event_to_json(event) + "\n" for event in events]
        with open(log_path, mode="a", encoding="utf-8") as f:
            lock.acquire(f)
            try:
                f.writelines(lines)
                f.flush()
            finally:
                lock.release(f)
    except Exception as e:
        logger.error("Failed to emit %s to %s: %s", what, log_path, e)
        raise


def append_jsonl_many(
    log_path: Path,
    events: Iterable[BaseEvent],
    *,
    lock: FileLock,
    logger: logging.Logger,
) -> None:
    """``emit_many``'s shared body: batch, skip a no-op empty batch, append.

    An empty batch opens nothing (``append_jsonl_batch`` is not called).
    """
    batch = list(events)
    if batch:
        append_jsonl_batch(log_path, batch, lock=lock, logger=logger, what=f"{len(batch)} events")


class JsonlAppendMixin:
    """Shared ``emit``/``emit_many`` for the two append-only JSONL writers.

    A mixed-in class sets ``log_path``, ``_lock`` (a `FileLock`) and
    ``_logger`` (its own module logger, so a failure is still attributed to
    the writer that hit it) in its own ``__init__``, and implements
    ``_emit_what`` for the label a single ``emit`` logs on failure. Both
    writers behave identically here; only that label differs between them.
    """

    log_path: Path
    _lock: FileLock
    _logger: logging.Logger

    def _emit_what(self, event: BaseEvent) -> str:
        raise NotImplementedError

    def emit(self, event: BaseEvent) -> None:
        """Append one event. Raises if the write fails; nothing is buffered."""
        append_jsonl_batch(
            self.log_path, [event], lock=self._lock, logger=self._logger, what=self._emit_what(event),
        )

    def emit_many(self, events: Iterable[BaseEvent]) -> None:
        """Append every event under one open, one lock and one flush.

        The batch is serialized before the log is opened, so a bad event
        leaves the file untouched. An empty batch opens nothing.
        """
        append_jsonl_many(self.log_path, events, lock=self._lock, logger=self._logger)
