"""SSE event-frame generator for the assistant turn stream.

Split out of _assistant_helpers.py (Task 10). ``_POLL_SECONDS``/``_IDLE_LIMIT``
are looked up on the ``_assistant_helpers`` facade at call time (rather than
read as this module's own globals) so tests patching
"quodeq.api._assistant_helpers._POLL_SECONDS"/"_IDLE_LIMIT" keep working
after the split.
"""
from __future__ import annotations

import time

from quodeq.assistant import AssistantStore

_POLL_SECONDS = 0.25
_IDLE_LIMIT = 2400  # 2400 * 0.25s = 600s idle backstop. The stream now stays
# open across turns (done/error no longer end event_frames), so this bounds a
# session that sits idle with NO new frames for the whole window — a turn that
# dies without emitting a terminal frame (e.g. a crashed daemon thread), or a
# session left open with no further turns. On the backstop the generator
# closes and the client reconnects on its next turn. Sized generously above
# the slowest legitimate gap (a cold-loading local model or a CLI provider's
# ~500s read timeout) so it never truncates a live turn.


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
    genuinely idle session (no new frames for the whole ``_IDLE_LIMIT``
    window) hits the backstop and closes; the client then reconnects on its
    next turn. Termination is therefore either that idle backstop or the
    client disconnecting (the generator is GC'd → ``GeneratorExit``). The
    traversal stays ordered by seq with ``last`` advancing so no frame is
    missed or duplicated.
    """
    from quodeq.api import _assistant_helpers as _helpers  # noqa: PLC0415 — deferred: see module docstring
    last, idle = after_seq, 0
    while idle < _helpers._IDLE_LIMIT:
        rows = repository.events_after(session_id, last)
        if not rows:
            idle += 1
            yield None
            time.sleep(_helpers._POLL_SECONDS)
            continue
        idle = 0
        for seq, frame in rows:
            last = seq
            yield seq, frame
