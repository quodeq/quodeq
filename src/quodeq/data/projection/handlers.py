from __future__ import annotations

import logging
from typing import Callable

from quodeq.core.events.models import (
    BaseEvent,
    EventType,
    FindingDismissedEvent,
    FindingUndismissedEvent,
    JudgmentCreatedEvent,
)
from quodeq.data.sqlite.state_store import SQLiteStateStore

_logger = logging.getLogger(__name__)


def _handle_judgment_created(event: JudgmentCreatedEvent, store: SQLiteStateStore) -> None:
    store.record_finding(event.payload)


def _handle_finding_dismissed(event: FindingDismissedEvent, store: SQLiteStateStore) -> None:
    payload = event.payload
    store.update_verdict(req=payload.req, file=payload.file, line=payload.line, verdict="dismissed")


def _handle_finding_undismissed(event: FindingUndismissedEvent, store: SQLiteStateStore) -> None:
    payload = event.payload
    # Restore the original violation verdict. (Compliance findings can't be dismissed
    # in the UI today, so 'violation' is the correct restore target.)
    store.update_verdict(req=payload.req, file=payload.file, line=payload.line, verdict="violation")


_HANDLERS: dict[EventType, Callable] = {
    EventType.JUDGMENT_CREATED: _handle_judgment_created,
    EventType.FINDING_DISMISSED: _handle_finding_dismissed,
    EventType.FINDING_UNDISMISSED: _handle_finding_undismissed,
}


def handle(event: BaseEvent, store: SQLiteStateStore) -> None:
    """Dispatch an event to its registered handler. Unknown types are skipped."""
    handler = _HANDLERS.get(event.event_type)
    if handler is None:
        _logger.debug("No handler for event type %s — skipping", event.event_type)
        return
    handler(event, store)
