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
            if streak >= self._threshold and self.trip_event is None:
                if not cancellation.is_cancelled():
                    event = TripEvent(streak=streak, recent=list(recent[-self._threshold:]))
                    self.trip_event = event
                    _logger.error(
                        "failure-streak breaker tripped: %d consecutive errors; recent=%s",
                        streak, [(e.file, e.reason) for e in event.recent],
                    )
                    cancellation.request_cancel()
                self._tripped.set()
                return  # one trip, then we're done
            self._stop.wait(timeout=_POLL_INTERVAL_S)

    def _scan_once(
        self, offset: int, streak: int, recent: list[FileError],
    ) -> tuple[int, int, list[FileError]]:
        try:
            with self._jsonl_path.open("rb") as f:
                f.seek(offset)
                chunk = f.read()
                new_offset = f.tell()
        except FileNotFoundError:
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
