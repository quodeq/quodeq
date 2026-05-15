from __future__ import annotations

from unittest.mock import MagicMock

from quodeq.core.events.models import (
    EventType,
    JudgmentCreatedEvent,
    JudgmentPayload,
)
from quodeq.data.projection.handlers import handle


def _judgment_event() -> JudgmentCreatedEvent:
    payload = JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file="f.py", line=1, reason="r",
    )
    return JudgmentCreatedEvent(payload=payload)


def test_judgment_created_calls_apply_judgment():
    store = MagicMock()
    event = _judgment_event()
    handle(event, store)
    store.apply_judgment.assert_called_once_with(event.payload)


def test_unknown_event_type_does_not_raise():
    store = MagicMock()
    event = MagicMock()
    event.event_type = EventType.RUN_STARTED  # no handler registered
    handle(event, store)
    store.apply_judgment.assert_not_called()
