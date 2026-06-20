"""Finding #355 — update_actions must continue past a failing handler.

When one event's handle() call raises, update_actions previously let the
exception bubble up and abort the loop. After the fix the bad event is
logged and skipped; subsequent events are still processed.
"""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.core.events.models import (
    BaseEvent,
    EventType,
    JudgmentCreatedEvent,
    JudgmentPayload,
)
from quodeq.data.projection.engine import ProjectionEngine
from quodeq.data.sqlite.state_store import SQLiteStateStore


def _good_event() -> JudgmentCreatedEvent:
    return JudgmentCreatedEvent(
        payload=JudgmentPayload(
            practice_id="P1", verdict="violation", dimension="Security",
            file="f.py", line=1, reason="r",
        )
    )


class _BadEvent:
    """Minimal event stub whose event_type is registered so handle() calls a real handler."""
    event_type = EventType.JUDGMENT_CREATED
    event_id = "bad-event-id"
    timestamp = None
    payload = None  # will cause handler to raise when it tries payload.practice_id etc.


def test_update_actions_continues_after_handler_error(tmp_path: Path, caplog):
    """A handler error must not abort the loop; later events must still be processed."""
    actions_log = tmp_path / "actions.jsonl"
    actions_log.write_text("")  # create file so stat() works

    good_event = _good_event()

    # Patch read_action_events to yield [bad, good] so we can assert the good
    # one is still processed despite the bad one raising.
    events_to_yield = [_BadEvent(), good_event]

    engine = ProjectionEngine()
    store = MagicMock(spec=SQLiteStateStore)
    store.get_actions_projected_size.return_value = None

    call_args_list = []

    def fake_handle(event, s):
        call_args_list.append(event)
        if isinstance(event, _BadEvent):
            raise ValueError("handler exploded on bad event")
        # For the good event, just return normally.

    # The quodeq root logger has propagate=False (shared/logging.py), so caplog
    # won't capture it via the normal propagation path. Add its handler directly.
    quodeq_logger = logging.getLogger("quodeq")
    quodeq_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR):
            with (
                patch("quodeq.data.actions_log.read_action_events", return_value=iter(events_to_yield)),
                patch("quodeq.data.projection.engine.SQLiteStateStore", return_value=store),
                patch("quodeq.data.projection.engine.handle", side_effect=fake_handle),
            ):
                applied = engine.update_actions(actions_log, tmp_path, force=True)
    finally:
        quodeq_logger.removeHandler(caplog.handler)

    # The good event must have been processed.
    assert applied == 1, f"Expected 1 applied (good event), got {applied}"
    # Both events were attempted.
    assert len(call_args_list) == 2
    # An error must have been logged for the bad event.
    assert any(r.levelno >= logging.ERROR for r in caplog.records), (
        f"Expected an ERROR log for the failing handler, got: {[r.message for r in caplog.records]}"
    )


def test_update_actions_does_not_abort_on_error(tmp_path: Path):
    """update_actions must not raise when a handler fails; it returns a count of successes."""
    actions_log = tmp_path / "actions.jsonl"
    actions_log.write_text("")

    def always_raise(event, store):
        raise RuntimeError("boom")

    engine = ProjectionEngine()
    with (
        patch("quodeq.data.actions_log.read_action_events", return_value=iter([_BadEvent(), _BadEvent()])),
        patch("quodeq.data.projection.engine.SQLiteStateStore", return_value=MagicMock(spec=SQLiteStateStore, get_actions_projected_size=MagicMock(return_value=None))),
        patch("quodeq.data.projection.engine.handle", side_effect=always_raise),
    ):
        # Must not raise — returns 0 successes.
        result = engine.update_actions(actions_log, tmp_path, force=True)

    assert result == 0
