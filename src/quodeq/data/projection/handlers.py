from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

from quodeq.core.events.models import (
    BaseEvent,
    EventType,
    JudgmentCreatedEvent,
)

_logger = logging.getLogger(__name__)


class StateStoreWriter(Protocol):
    """The slice of the state store the event handlers write through.

    ``SQLiteStateStore`` satisfies it in production; tests hand in fakes so
    handler logic runs without a database file. Dismiss/undismiss events are
    not handled here: the actions log is folded into a net state and applied
    in one pass (``ProjectionEngine.update_actions``), since a per-event
    replay cannot un-apply a line match that a later fingerprinted entry
    supersedes.
    """

    def record_finding(self, payload: Any) -> None: ...


def _handle_judgment_created(event: JudgmentCreatedEvent, store: StateStoreWriter) -> None:
    store.record_finding(event.payload)


_HANDLERS: dict[EventType, Callable] = {
    EventType.JUDGMENT_CREATED: _handle_judgment_created,
}


def handle(event: BaseEvent, store: StateStoreWriter) -> None:
    """Dispatch an event to its registered handler. Unknown types are skipped."""
    handler = _HANDLERS.get(event.event_type)
    if handler is None:
        _logger.debug("No handler for event type %s — skipping", event.event_type)
        return
    handler(event, store)
