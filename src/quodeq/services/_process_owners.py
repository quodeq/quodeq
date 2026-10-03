"""One process instance each of the walk cache, the live-tally memo, and the
score-cache single-flight registry.

These are the G3 (process-scoped) owners: exactly one per process, created
here at import time -- the composition root for state that used to live as
bare module globals in ``_accumulated_cache.py``, ``_scan_progress_dims.py``
and ``_score_cache_fetch.py``. Never create a second instance per request;
consumers default to these via a keyword-only ``... | None = None`` param,
resolved inside the function body (never as the parameter's default value
itself), so an explicitly-passed instance (tests, per-call isolation) always
wins.

``services/wiring.py`` re-exports the three ``DEFAULT_*`` instances (plus the
owner classes, for callers that need to build their own for isolation) in one
line, so consumer modules reach them the same way they reach every other
services -> data concretion.

``SingleFlight`` is defined here rather than in ``_score_cache_fetch.py``
(where it is used) because that module reaches its shared instance through
``services.wiring``, which re-exports from this module -- defining the class
where it is consumed would import this module from that one and back again.
``WalkCache`` has no such constraint (``_accumulated_cache.py`` never needs
the *instance* back, only ``clear_accumulated_process_cache`` does, via a
deferred import) so it stays defined next to the state it replaces.
``LiveTallyMemo`` moved to its own module, ``_live_tally_memo.py``, instead.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from quodeq.services._accumulated_cache import WalkCache, walk_cache_max
from quodeq.services._live_tally_memo import LIVE_TALLY_MEMO_SIZE, LiveTallyMemo


class SingleFlight:
    """Ensures concurrent callers for one key share a single in-progress compute.

    Concurrent misses on the same key must share ONE compute: some computes
    walk a project's full run history and can take minutes right after an
    upgrade invalidates every cached row, and a client re-requests while the
    first compute is still running. The per-key lock is dropped once no
    thread holds it; a waiter that raced the cleanup at worst recomputes
    (idempotent write).
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[tuple, threading.Lock] = {}

    @contextmanager
    def hold(self, key: tuple) -> Iterator[None]:
        """Serialise callers sharing *key*; the first in builds, the rest wait."""
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        lock.acquire()
        try:
            yield
        finally:
            lock.release()
            with self._guard:
                if not lock.locked() and self._locks.get(key) is lock:
                    del self._locks[key]


DEFAULT_WALK_CACHE = WalkCache(max_fn=walk_cache_max)
DEFAULT_LIVE_TALLY_MEMO = LiveTallyMemo(size=LIVE_TALLY_MEMO_SIZE)
DEFAULT_SINGLE_FLIGHT = SingleFlight()
