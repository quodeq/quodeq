"""Atomic, bounded "already-scored" claims owner shared by the evaluation routes.

Tracks job_ids whose background scoring has already been claimed so that
repeated GETs for the same job never spawn more than one scoring thread.
One instance lives per Flask app (``app.extensions["scoring_claims"]``),
created at the composition root (``api/app.py``'s ``create_app``) and shared
by request threads and the background runner.

Uses an OrderedDict as a bounded LRU so the registry cannot grow without
limit on a long-running server. Access is serialised by a Lock so the
check-then-add is atomic (closing the TOCTOU race that a plain ``set``
would have).
"""
from __future__ import annotations

import threading
from collections import OrderedDict

SCORED_JOBS_MAX = 1000


class ScoringClaims:
    """Job ids whose scoring is claimed. One per app. LRU-bounded like the old dict."""

    def __init__(self, max_entries: int = SCORED_JOBS_MAX) -> None:
        self._lock = threading.Lock()
        self._claimed: OrderedDict[str, None] = OrderedDict()
        self._max = max_entries

    def claim(self, job_id: str) -> bool:
        """Atomically claim *job_id* for one-time background scoring.

        Returns ``True`` if this caller should start the scoring thread;
        ``False`` if another caller already claimed it.

        Bounded to ``max_entries`` (oldest-first eviction) so memory usage
        stays constant regardless of server uptime.
        """
        with self._lock:
            if job_id in self._claimed:
                return False
            self._claimed[job_id] = None
            while len(self._claimed) > self._max:
                self._claimed.popitem(last=False)  # evict oldest entry
            return True

    def release(self, job_id: str) -> None:
        """Release a claim taken by :meth:`claim`.

        Used when a discard-cancel claims the slot up front but the cancel
        itself fails: without the release, a later legitimate cancel of the
        same job would never get its completed dims scored.
        """
        with self._lock:
            self._claimed.pop(job_id, None)

    def reset(self) -> None:
        """Clear every claim. Useful for test isolation."""
        with self._lock:
            self._claimed.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._claimed)
