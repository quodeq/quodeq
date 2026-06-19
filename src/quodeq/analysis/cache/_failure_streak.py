"""Consecutive-failure circuit breaker for the dim runner.

Tails the dim's evidence JSONL for file_done markers, counts consecutive
errors, signals run-wide cancellation when the threshold trips. Reuses
the same cancellation event that SIGTERM triggers, so workers and the
existing dispatch teardown handle the rest.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

from quodeq.shared import cancellation

_logger = logging.getLogger(__name__)

# How often the watcher re-reads the JSONL to find new lines. Small
# enough that a trip happens within ~poll_interval of the threshold-th
# error, large enough that we don't spin.
_POLL_INTERVAL_S = 0.5


class CircuitBreakerError(Exception):
    """Raised by the dim runner when the failure-streak watcher trips.

    Carries the breaker reason so RunLifecycleContext.__exit__ can map
    it to exit_reason='failure_streak' on the run-level status.
    """

    def __init__(self, reason: str = "circuit_breaker") -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class FileError:
    file: str
    reason: str


@dataclass
class TripEvent:
    streak: int
    recent: list[FileError] = field(default_factory=list)


class FailureStreakWatcher:
    """Background watcher that trips cancellation on N consecutive errors."""

    def __init__(self, jsonl_path: Path, *, threshold: int):
        self._jsonl_path = jsonl_path
        self._threshold = threshold
        self._stop = threading.Event()
        self._tripped = threading.Event()
        self._thread: threading.Thread | None = None
        self.trip_event: TripEvent | None = None

    def start(self) -> None:
        if self._threshold <= 0:
            # Still start a no-op thread so callers can rely on stop_and_join.
            self._thread = threading.Thread(target=self._noop, daemon=True)
        else:
            self._thread = threading.Thread(
                target=self._run, daemon=True,
                name=f"failure-streak-{self._jsonl_path.stem}",
            )
        self._thread.start()

    def stop_and_join(self, *, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def wait_for_trip(self, *, timeout: float) -> bool:
        return self._tripped.wait(timeout=timeout)

    def _noop(self) -> None:
        self._stop.wait()

    def _run(self) -> None:
        offset = 0
        streak = 0
        recent: list[FileError] = []
        while not self._stop.is_set():
            offset, streak, recent = self._scan_once(offset, streak, recent)
            if self._maybe_trip(streak, recent):
                return  # one trip, then we're done
            self._stop.wait(timeout=_POLL_INTERVAL_S)
        # Stop was signaled (dispatch finished or raised). Do one last scan so
        # a streak written since the previous poll still trips. Without it, a
        # dispatch that fails fast and returns within a single poll interval
        # (a dead endpoint erroring every file, or a time-compressed test) can
        # finish *between* polls -- the loop then exits at the top check having
        # never scanned the errors, and the breaker misses a trip it should
        # have caught. This mirrors the periodic-persist watcher's
        # final-persist-on-stop guarantee and makes the trip independent of
        # poll timing (the slow-runner flake).
        offset, streak, recent = self._scan_once(offset, streak, recent)
        self._maybe_trip(streak, recent)

    def _maybe_trip(self, streak: int, recent: list[FileError]) -> bool:
        """Record a trip when the consecutive-error streak hits the threshold.

        Idempotent and safe to call after stop: only the first trip sets
        ``trip_event`` and requests cancellation. Returns True once a trip is
        registered so the poll loop knows to stop. If the run is already
        cancelling for another reason, set ``_tripped`` but leave
        ``trip_event`` None -- the breaker must not claim a cancellation it
        didn't cause (preserves the prior behavior).
        """
        if streak < self._threshold or self.trip_event is not None:
            return False
        if not cancellation.is_cancelled():
            event = TripEvent(streak=streak, recent=list(recent[-self._threshold:]))
            self.trip_event = event
            _logger.error(
                "failure-streak breaker tripped: %d consecutive errors; recent=%s",
                streak, [(e.file, e.reason) for e in event.recent],
            )
            cancellation.request_cancel()
        self._tripped.set()
        return True

    def _scan_once(
        self, offset: int, streak: int, recent: list[FileError],
    ) -> tuple[int, int, list[FileError]]:
        try:
            with self._jsonl_path.open("rb") as f:
                f.seek(offset)
                chunk = f.read()
                new_offset = f.tell()
        except OSError as e:
            _logger.warning("Could not read failure-streak JSONL %s: %s", self._jsonl_path, e)
            return offset, streak, recent
        for raw in chunk.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if entry.get("_marker") != "file_done":
                continue
            status = entry.get("status")
            if status == "ok":
                streak = 0
                recent = []
            elif status == "error":
                streak += 1
                recent.append(FileError(
                    file=str(entry.get("file", "?")),
                    reason=str(entry.get("reason", "")),
                ))
        return new_offset, streak, recent
