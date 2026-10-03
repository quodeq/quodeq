"""Server-sent-event frame primitives shared by every SSE route.

``sse_line`` renders one frame. The heartbeat helpers give a quiet stream a
*data* event to send: SSE comments (``:keepalive``) keep proxies from closing
the socket but never reach the browser's ``EventSource`` listeners, so only a
real event can stop the client's inactivity timer from tripping on a run that
is alive but silent.
"""
from __future__ import annotations

from enum import StrEnum


class SseEvent(StrEnum):
    """Named events the run and job-log streams send (mirrored by
    src/quodeq/ui/src/vocab/sseEvent.js)."""

    STATUS = "status"
    DIMENSION_COMPLETED = "dimension-completed"
    FINDING = "finding"
    DONE = "done"
    HEARTBEAT = "heartbeat"


HEARTBEAT_EVENT = SseEvent.HEARTBEAT
HEARTBEAT_MS = 15_000


def sse_line(data: str, event: str | None = None, event_id: int | None = None) -> str:
    """Render one server-sent-event frame: optional id and event, then data.

    The trailing blank line is what makes the browser dispatch the event, so
    every frame the API writes goes through here rather than being
    assembled at the call site.
    """
    parts = []
    if event_id is not None:
        parts.append(f"id: {event_id}\n")
    if event is not None:
        parts.append(f"event: {event}\n")
    parts.append(f"data: {data}\n\n")
    return "".join(parts)


def heartbeat_frame() -> str:
    """The ``event: heartbeat`` frame a quiet stream sends to prove it is alive."""
    return sse_line("{}", event=HEARTBEAT_EVENT)


class Heartbeat:
    """Tracks silence on a stream and says when a heartbeat frame is due.

    ``advance(ms)`` accounts for time spent without emitting data; ``reset()``
    is called when real data went out. Both keep the cadence at HEARTBEAT_MS.
    """

    def __init__(self, interval_ms: int = HEARTBEAT_MS) -> None:
        self._interval_ms = interval_ms
        self._quiet_ms = 0

    def reset(self) -> None:
        """Real data went out; start counting silence from zero again."""
        self._quiet_ms = 0

    def advance(self, elapsed_ms: int) -> str | None:
        """Add *elapsed_ms* of silence; return the frame to send when one is due."""
        self._quiet_ms += elapsed_ms
        if self._quiet_ms < self._interval_ms:
            return None
        self._quiet_ms = 0
        return heartbeat_frame()
