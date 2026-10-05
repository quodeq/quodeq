"""Lock-guarded status of a single-slot background job.

The shared-repo publish and connect jobs each keep one process-wide slot:
a status dict the worker thread updates and the status route snapshots.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from enum import StrEnum

# The status field that times each phase: an ordered list of
# ``[phase, unix seconds it started]``, one entry per change of ``phase``.
# A list, not a dict keyed by phase: a clone that retries (a shallow attempt,
# then a full one) passes through downloading again, and each pass must keep
# its own start or the log books the failed attempt to the wrong phase.
PHASE_TIMES_FIELD = "phase_times"


def phase_durations(snapshot: Mapping[str, object], finished_at: float | None = None) -> str:
    """One entry per phase pass with its length, for the server log: ``downloading 12.3s · resolving 4.1s``.

    Entries are read in the order they started; the last one ends at
    *finished_at* (now when absent). Empty when the job timed nothing.
    """
    times = snapshot.get(PHASE_TIMES_FIELD) or []
    if not isinstance(times, list) or not times:
        return ""
    end = finished_at if finished_at is not None else time.time()
    parts = []
    for i, (phase, started) in enumerate(times):
        stop = times[i + 1][1] if i + 1 < len(times) else end
        parts.append(f"{phase} {max(0.0, stop - started):.1f}s")
    return " · ".join(parts)


class JobSlotStatus:
    """A status dict behind a lock, with an atomic claim of the job slot.

    *idle* holds every field with its idle value, including ``state``.
    Claiming resets all fields to *idle*, then sets ``state`` to *running*
    plus the fields the claim names. Every change of ``phase`` is stamped in
    ``phase_times`` (a fresh dict per job, never the idle one).
    """

    def __init__(self, idle: Mapping[str, object], running: StrEnum, *, clock: Callable[[], float] = time.time) -> None:
        self._lock = threading.Lock()
        self._idle = dict(idle)
        self._running = running
        self._status = dict(idle)
        self._clock = clock

    def copy(self) -> dict:
        """Return a snapshot of the status fields, safe to hand to a route."""
        with self._lock:
            return dict(self._status)

    def set(self, **fields) -> None:
        """Merge *fields* into the status. Keys are not validated."""
        with self._lock:
            self._status.update(self._stamped(fields))

    def claim_slot(self, **fields) -> bool:
        """Atomically take the slot with *fields*; False while a job is running."""
        with self._lock:
            if self._status["state"] == self._running:
                return False
            self._status = {**self._idle, "state": self._running}
            self._status.update(self._stamped(fields))
            return True

    def _stamped(self, fields: Mapping[str, object]) -> dict:
        """*fields*, plus a new ``phase_times`` when they move ``phase``. Lock held by the caller."""
        phase = fields.get("phase")
        if phase is None or phase == self._status.get("phase"):
            return dict(fields)
        times = list(self._status.get(PHASE_TIMES_FIELD) or [])
        times.append([str(phase), self._clock()])
        return {**fields, PHASE_TIMES_FIELD: times}
