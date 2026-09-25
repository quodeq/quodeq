"""Atomic, bounded "already-scored" registry shared by the evaluation routes.

Keeps track of job_ids whose background scoring has already been claimed so
that repeated GETs for the same job never spawn more than one scoring thread.

Uses an OrderedDict as a bounded LRU so the registry cannot grow without
limit on a long-running server. Access is serialised by a Lock so the
check-then-add is atomic (closing the TOCTOU race that a plain ``set``
would have).
"""
from __future__ import annotations

import threading
from collections import OrderedDict

scored_jobs: "OrderedDict[str, None]" = OrderedDict()
scored_jobs_lock = threading.Lock()
SCORED_JOBS_MAX = 1000


def claim_scoring(job_id: str) -> bool:
    """Atomically claim *job_id* for one-time background scoring.

    Returns ``True`` if this caller should start the scoring thread;
    ``False`` if another caller already claimed it.

    The registry is bounded to ``SCORED_JOBS_MAX`` entries (LRU eviction)
    so memory usage stays constant regardless of server uptime.
    """
    with scored_jobs_lock:
        if job_id in scored_jobs:
            return False
        scored_jobs[job_id] = None
        while len(scored_jobs) > SCORED_JOBS_MAX:
            scored_jobs.popitem(last=False)  # evict oldest entry
        return True


def release_scoring(job_id: str) -> None:
    """Release a claim taken by :func:`claim_scoring`.

    Used when a discard-cancel claims the slot up front but the cancel
    itself fails: without the release, a later legitimate cancel of the
    same job would never get its completed dims scored.
    """
    with scored_jobs_lock:
        scored_jobs.pop(job_id, None)


def reset_scored_jobs() -> None:
    """Clear the scored-jobs registry. Useful for test isolation."""
    with scored_jobs_lock:
        scored_jobs.clear()
