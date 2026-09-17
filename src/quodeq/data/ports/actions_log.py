"""Write protocol for the per-project action log."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from quodeq.core.events.models import BaseEvent


@runtime_checkable
class ActionLog(Protocol):
    """Write seam for the project action log (dismiss/verify/delete events).

    Mirrors the public surface of the concrete
    ``quodeq.data.actions_log.ActionLogWriter`` that callers actually use:
    appending one event, or one batch. Consumers type against this Protocol
    so a fake writer can stand in for isolated tests.
    """

    def emit(self, event: BaseEvent) -> None:
        """Append *event* to the log."""
        ...

    def emit_many(self, events: Iterable[BaseEvent]) -> None:
        """Append every event in *events* as one write."""
        ...
