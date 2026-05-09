"""Consecutive-failure circuit breaker for the dim runner."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from quodeq.shared import cancellation
from quodeq.analysis.cache._failure_streak import (
    FailureStreakWatcher,
    TripEvent,
    CircuitBreakerError,
)


def _append(jsonl: Path, line: dict) -> None:
    with jsonl.open("a") as f:
        f.write(json.dumps(line) + "\n")


@pytest.fixture(autouse=True)
def _reset_cancel():
    cancellation.reset()
    yield
    cancellation.reset()


class TestFailureStreakBreaker:
    def test_no_trip_with_streak_below_threshold(self, tmp_path: Path):
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.touch()
        watcher = FailureStreakWatcher(jsonl, threshold=5)
        watcher.start()
        for _ in range(4):
            _append(jsonl, {"_marker": "file_done", "file": "x", "status": "error", "reason": "token_limit"})
        _append(jsonl, {"_marker": "file_done", "file": "x", "status": "ok"})
        for _ in range(4):
            _append(jsonl, {"_marker": "file_done", "file": "x", "status": "error", "reason": "token_limit"})
        watcher.stop_and_join(timeout=5.0)
        assert not cancellation.is_cancelled()
        assert watcher.trip_event is None

    def test_trip_at_threshold(self, tmp_path: Path):
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.touch()
        watcher = FailureStreakWatcher(jsonl, threshold=5)
        watcher.start()
        for i in range(5):
            _append(jsonl, {"_marker": "file_done", "file": f"f{i}.py", "status": "error", "reason": "token_limit"})
        watcher.wait_for_trip(timeout=5.0)
        watcher.stop_and_join(timeout=5.0)
        assert cancellation.is_cancelled()
        assert isinstance(watcher.trip_event, TripEvent)
        assert watcher.trip_event.streak == 5
        assert len(watcher.trip_event.recent) == 5
        assert watcher.trip_event.recent[0].reason == "token_limit"

    def test_threshold_zero_disables(self, tmp_path: Path):
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.touch()
        watcher = FailureStreakWatcher(jsonl, threshold=0)
        watcher.start()
        for _ in range(100):
            _append(jsonl, {"_marker": "file_done", "file": "x", "status": "error"})
        watcher.stop_and_join(timeout=5.0)
        assert not cancellation.is_cancelled()

    def test_threshold_one_trips_immediately(self, tmp_path: Path):
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.touch()
        watcher = FailureStreakWatcher(jsonl, threshold=1)
        watcher.start()
        _append(jsonl, {"_marker": "file_done", "file": "x", "status": "error", "reason": "parse_error"})
        watcher.wait_for_trip(timeout=5.0)
        watcher.stop_and_join(timeout=5.0)
        assert cancellation.is_cancelled()

    def test_already_cancelled_does_not_double_trip(self, tmp_path: Path):
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.touch()
        cancellation.request_cancel()
        watcher = FailureStreakWatcher(jsonl, threshold=5)
        watcher.start()
        for _ in range(10):
            _append(jsonl, {"_marker": "file_done", "file": "x", "status": "error"})
        watcher.stop_and_join(timeout=5.0)
        # The watcher sees cancellation already set and does not record a trip event.
        assert watcher.trip_event is None


class TestCircuitBreakerError:
    def test_error_has_reason(self):
        exc = CircuitBreakerError("circuit_breaker")
        assert str(exc) == "circuit_breaker"
        assert exc.reason == "circuit_breaker"

    def test_default_reason(self):
        exc = CircuitBreakerError()
        assert exc.reason == "circuit_breaker"
