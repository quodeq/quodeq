"""Lock-guarded status of a single-slot background job.

The shared-repo publish and connect jobs each keep one process-wide slot:
a status dict the worker thread updates and the status route snapshots.
"""
from __future__ import annotations

import threading
from collections.abc import Mapping
from enum import StrEnum


class JobSlotStatus:
    """A status dict behind a lock, with an atomic claim of the job slot.

    *idle* holds every field with its idle value, including ``state``.
    Claiming resets all fields to *idle*, then sets ``state`` to *running*
    plus the fields the claim names.
    """

    def __init__(self, idle: Mapping[str, object], running: StrEnum) -> None:
        self._lock = threading.Lock()
        self._idle = dict(idle)
        self._running = running
        self._status = dict(idle)

    def copy(self) -> dict:
        """Return a snapshot of the status fields, safe to hand to a route."""
        with self._lock:
            return dict(self._status)

    def set(self, **fields) -> None:
        """Merge *fields* into the status. Keys are not validated."""
        with self._lock:
            self._status.update(fields)

    def claim_slot(self, **fields) -> bool:
        """Atomically take the slot with *fields*; False while a job is running."""
        with self._lock:
            if self._status["state"] == self._running:
                return False
            self._status = {**self._idle, "state": self._running, **fields}
            return True
