"""SSE event-frame generator for the assistant turn stream.

Split out of _assistant_helpers.py. ``POLL_SECONDS``/``IDLE_LIMIT`` are read
as this module's own globals (not looked up on the ``_assistant_helpers``
facade) so this module never imports back the facade that re-exports it.
Tests patch "quodeq.api._assistant_events.POLL_SECONDS"/"IDLE_LIMIT".
"""
from __future__ import annotations

import time

from quodeq.assistant import AssistantStore

POLL_SECONDS = 0.25
# Idle backstop: 2400 polls x 0.25s = 600s with no new frame closes the
# stream (the client reconnects on its next turn). It bounds a turn that
# dies without a terminal frame; sized above the slowest legitimate gap (a
# cold local model, a CLI provider's ~500s read timeout).
IDLE_LIMIT = 2400


def event_frames(repository: AssistantStore, session_id: str, after_seq: int):
    """Generator of (seq, frame) tuples or ``None`` heartbeats.

    Replays stored events after ``after_seq``, then polls indefinitely,
    yielding new events (and ``None`` heartbeat sentinels while idle) so a
    SINGLE SSE connection serves EVERY turn in the session, not just the
    first. ``done``/``error`` frames are still yielded — the client uses them
    as turn markers to clear its spinner and start a fresh answer bubble — but
    they no longer end the generator, so a second (or third) turn's frames,
    appended after the first turn's ``done``, still reach the browser.

    Each idle tick with no new rows yields ``None`` (a heartbeat sentinel the
    caller turns into an SSE comment / data frame) instead of sleeping
    silently, so slow-starting local models and long gaps between frames — or
    between turns — don't trip proxy/connection idle timeouts. The idle
    counter resets on ANY new event (including across turns), so only a
    genuinely idle session (no new frames for the whole ``IDLE_LIMIT``
    window) hits the backstop and closes; the client then reconnects on its
    next turn. Termination is therefore either that idle backstop or the
    client disconnecting (the generator is GC'd → ``GeneratorExit``). The
    traversal stays ordered by seq with ``last`` advancing so no frame is
    missed or duplicated.
    """
    last, idle = after_seq, 0
    while idle < IDLE_LIMIT:
        rows = repository.events_after(session_id, last)
        if not rows:
            idle += 1
            yield None
            time.sleep(POLL_SECONDS)
            continue
        idle = 0
        for seq, frame in rows:
            last = seq
            yield seq, frame
