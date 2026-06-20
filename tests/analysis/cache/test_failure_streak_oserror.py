"""Tests for _failure_streak.py — OSError handling in _scan_once."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from quodeq.shared import cancellation
from quodeq.analysis.cache._failure_streak import FailureStreakWatcher


def _append(jsonl: Path, line: dict) -> None:
    with jsonl.open("a") as f:
        f.write(json.dumps(line) + "\n")


def _enable_propagation():
    logger = logging.getLogger("quodeq")
    original = logger.propagate
    logger.propagate = True
    return logger, original


@pytest.fixture(autouse=True)
def _reset_cancel():
    cancellation.reset()
    yield
    cancellation.reset()


class TestScanOnceOSError:
    def test_permission_error_returns_unchanged_state_and_logs_warning(
        self, tmp_path: Path, caplog
    ):
        """#377 — PermissionError (OSError subclass) on open must log WARNING and
        return the unchanged (offset, streak, recent) state, not only catch FileNotFoundError."""
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.touch()

        watcher = FailureStreakWatcher(jsonl, threshold=10)

        quodeq_logger, orig = _enable_propagation()
        try:
            with patch.object(
                Path, "open", side_effect=PermissionError("access denied")
            ):
                with caplog.at_level(
                    logging.WARNING, logger="quodeq.analysis.cache._failure_streak"
                ):
                    offset, streak, recent = watcher._scan_once(0, 3, [])
        finally:
            quodeq_logger.propagate = orig

        # State is unchanged
        assert offset == 0
        assert streak == 3
        assert recent == []
        # Warning was logged
        assert "Could not read failure-streak JSONL" in caplog.text

    def test_filenot_found_still_returns_unchanged_state(self, tmp_path: Path):
        """FileNotFoundError (already handled) still returns unchanged state."""
        jsonl = tmp_path / "missing.jsonl"
        watcher = FailureStreakWatcher(jsonl, threshold=5)
        offset, streak, recent = watcher._scan_once(99, 2, [])
        assert offset == 99
        assert streak == 2
        assert recent == []
