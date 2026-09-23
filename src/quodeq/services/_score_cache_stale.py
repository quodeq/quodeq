"""Stale-while-revalidate slots for the accumulated read-through cache.

A running eval re-keys the accumulated version with every finding it writes
(an in-flight run's key set feeds the hash), so the exact-version cache never
hits and single-flight cannot merge requests whose versions differ. Each
slot holds the last payload computed under one *stale scope*: the version
minus the in-flight runs' keys (see ``score_cache.accumulated_stale_scope``).
A miss inside the scope serves that payload and refreshes it on one
background thread, so readers never wait on, or pile up behind, a recompute.
In-process only: a restart pays one synchronous compute per scope.
"""
from __future__ import annotations

import sqlite3
import threading
from collections import OrderedDict
from typing import Callable

from quodeq.core.observability import LogSink

Slot = tuple[str, str, str]

# Bounded: one slot per (project, as_of) view in use, and a payload can be
# megabytes on a long history, so evict the least recently used.
_SLOTS_MAX = 8
_GUARD = threading.Lock()
_PAYLOADS: OrderedDict[Slot, dict] = OrderedDict()
_REFRESHING: set[Slot] = set()


def recall(slot: Slot) -> dict | None:
    """The last payload stored for *slot*, or None."""
    with _GUARD:
        payload = _PAYLOADS.get(slot)
        if payload is not None:
            _PAYLOADS.move_to_end(slot)
        return payload


def remember(slot: Slot, payload: dict) -> None:
    """Store *payload* as the latest for *slot*."""
    with _GUARD:
        _PAYLOADS[slot] = payload
        _PAYLOADS.move_to_end(slot)
        while len(_PAYLOADS) > _SLOTS_MAX:
            _PAYLOADS.popitem(last=False)


def refresh_in_background(slot: Slot, refresh: Callable[[], dict], log: LogSink) -> None:
    """Run *refresh* on a daemon thread and store its result, unless one is already running."""
    with _GUARD:
        if slot in _REFRESHING:
            return
        _REFRESHING.add(slot)

    def run() -> None:
        try:
            remember(slot, refresh())
        except (OSError, sqlite3.Error, ValueError) as exc:
            # The slot keeps serving its stale payload; the next miss retries.
            # Anything else propagates to threading.excepthook (the finally
            # still frees the slot).
            log.warning(f"background accumulated refresh failed for {slot[1]}: {exc}")
        finally:
            with _GUARD:
                _REFRESHING.discard(slot)

    threading.Thread(target=run, name=f"accumulated-refresh-{slot[1]}", daemon=True).start()


def clear_stale_payloads() -> None:
    """Drop every slot (tests: module state must not leak between cases)."""
    with _GUARD:
        _PAYLOADS.clear()
