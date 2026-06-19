"""Tests for engine.py — except breadth narrowing (#528).

The handler's broad `except Exception` must be narrowed to
`(ValueError, KeyError, TypeError)` so OS/SQLite errors surface instead of
being silently logged and skipped.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.data.projection.engine import ProjectionEngine
from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter


def _write_one_event(log: Path) -> None:
    writer = EventLogWriter(log)
    writer.emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file="f.py", line=1, reason="r",
    )))


class TestProjectionEngineExceptBreadth:
    def test_value_error_in_handler_is_caught_and_logged(self, tmp_path: Path, caplog):
        """ValueError from a handler is swallowed and the next event proceeds."""
        import logging
        log = tmp_path / "events.jsonl"
        _write_one_event(log)
        engine = ProjectionEngine()

        with patch("quodeq.data.projection.engine.handle", side_effect=ValueError("bad value")):
            import logging as _logging
            qlog = _logging.getLogger("quodeq")
            orig = qlog.propagate
            qlog.propagate = True
            try:
                with caplog.at_level(logging.ERROR, logger="quodeq.data.projection.engine"):
                    count = engine.rebuild(log, tmp_path)
            finally:
                qlog.propagate = orig

        # Event was attempted but failed; count = 0 (skipped)
        assert count == 0
        assert "Handler failed" in caplog.text

    def test_os_error_in_handler_propagates(self, tmp_path: Path):
        """#528 — OSError must NOT be swallowed by the narrowed except clause."""
        log = tmp_path / "events.jsonl"
        _write_one_event(log)
        engine = ProjectionEngine()

        with patch(
            "quodeq.data.projection.engine.handle", side_effect=OSError("disk gone")
        ):
            with pytest.raises(OSError, match="disk gone"):
                engine.rebuild(log, tmp_path)
