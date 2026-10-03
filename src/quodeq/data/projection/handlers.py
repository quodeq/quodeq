"""Per-event-type handlers the projection dispatches through."""
from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

from quodeq.core.admission import Admitted
from quodeq.core.events.models import (
    BaseEvent,
    EventType,
    JudgmentCreatedEvent,
)
from quodeq.data.projection.admission import Admitter, placed, unmapped_reason

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

    def record_finding(self, payload: Any) -> None:
        """Persist one judgment payload. Re-projecting the same event is a no-op."""
        ...

    def record_unmapped(self, payload: Any, reason: str) -> None:
        """Keep one judgment the standard cannot place, out of the graded findings."""
        ...


def _handle_judgment_created(
    event: JudgmentCreatedEvent, store: StateStoreWriter, admitter: Admitter | None,
) -> None:
    payload = event.payload
    if admitter is None:
        store.record_finding(payload)
        return
    result = admitter(payload)
    reason = unmapped_reason(payload, result)
    if reason is not None:
        store.record_unmapped(payload, reason)
    elif isinstance(result, Admitted):
        store.record_finding(placed(payload, result))
    else:
        store.record_finding(payload)


_HANDLERS: dict[EventType, Callable] = {
    EventType.JUDGMENT_CREATED: _handle_judgment_created,
}


def handle(event: BaseEvent, store: StateStoreWriter, admitter: Admitter | None = None) -> None:
    """Dispatch an event to its registered handler. Unknown types are skipped.

    *admitter* places finding events in their standard; None stores them as
    reported (tests and tools that project raw events).
    """
    handler = _HANDLERS.get(event.event_type)
    if handler is None:
        _logger.debug("No handler for event type %s — skipping", event.event_type)
        return
    handler(event, store, admitter)
