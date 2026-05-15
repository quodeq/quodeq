from __future__ import annotations

import logging
from typing import Callable

from quodeq.core.events.models import BaseEvent, EventType, JudgmentCreatedEvent
from quodeq.data.sqlite.state_store import SQLiteStateStore

_logger = logging.getLogger(__name__)


def _handle_judgment_created(event: JudgmentCreatedEvent, store: SQLiteStateStore) -> None:
    store.record_finding(event.payload)


_HANDLERS: dict[EventType, Callable] = {
    EventType.JUDGMENT_CREATED: _handle_judgment_created,
}


def handle(event: BaseEvent, store: SQLiteStateStore) -> None:
    """Dispatch an event to its registered handler. Unknown types are skipped."""
    handler = _HANDLERS.get(event.event_type)
    if handler is None:
        _logger.debug("No handler for event type %s — skipping", event.event_type)
        return
    handler(event, store)
