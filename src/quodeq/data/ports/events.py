"""Port: event-emitter protocol for the run event log.

``analysis`` orchestration emits run events (``events.jsonl``) through this
protocol instead of constructing the concrete
:class:`quodeq.data.events.writer.EventLogWriter` itself. The default
resolution (a lazy ``EventLogWriter`` import) lives at the call site in
``analysis/cache/dimension_runner.py``; tests inject a recording fake.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from quodeq.core.events.models import BaseEvent


@runtime_checkable
class EventEmitter(Protocol):
    """Append-only sink for run events (matches ``EventLogWriter.emit``)."""

    def emit(self, event: BaseEvent) -> None: ...
