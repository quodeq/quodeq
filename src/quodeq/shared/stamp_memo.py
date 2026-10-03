"""In-process memo keyed by an on-disk stamp.

A read that only depends on some files' contents can be reused while those
files have not changed. A stamp is whatever tuple identifies the inputs
(``file_stamp`` gives one file's mtime and size; callers combine several).
The stamp is taken before the read, so a write racing the read only costs
one extra recompute.

Bounded by a wholesale clear rather than an LRU: the set of keys a process
visits is small and stable, so the bound only guards against unbounded
growth.
"""
from __future__ import annotations

import sys
import threading
import weakref
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from quodeq.shared import request_metrics

T = TypeVar("T")

MEMO_MAX = 4096
# Entries sampled when estimating a cache's size: deep-measuring every
# multi-megabyte payload would cost more than the debug read is worth.
_SIZE_SAMPLE = 8

#: Every live StampCache, for the runtime metrics endpoint.
CACHES: weakref.WeakSet[StampCache] = weakref.WeakSet()


class StampCache:
    """Stamp-keyed store, bounded by a wholesale clear.

    *name* identifies the cache in ``/api/debug/metrics``; hit and miss
    totals accumulate for the life of the process.
    """

    def __init__(self, max_entries: int = MEMO_MAX, name: str = "anonymous") -> None:
        self._entries: dict[str, tuple[tuple, object]] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries
        self.name = name
        self.hits = 0
        self.misses = 0
        CACHES.add(self)

    def get(self, key: str, stamp: tuple) -> object | None:
        """The value stored for *key* under *stamp*, or None when it is not current."""
        with self._lock:
            hit = self._entries.get(key)
        if hit is None or hit[0] != stamp:
            self.misses += 1
            request_metrics.count("cache_misses")
            return None
        self.hits += 1
        request_metrics.count("cache_hits")
        return hit[1]

    def stats(self) -> dict[str, object]:
        """Entry count, hit/miss totals and an approximate byte size."""
        with self._lock:
            values = [entry[1] for entry in self._entries.values()]
        sampled = values[:_SIZE_SAMPLE]
        per_entry = sum(approx_size(v) for v in sampled) / len(sampled) if sampled else 0
        return {
            "name": self.name, "entries": len(values), "max_entries": self._max_entries,
            "hits": self.hits, "misses": self.misses, "approx_bytes": int(per_entry * len(values)),
        }

    def put(self, key: str, stamp: tuple, value: object) -> None:
        """Store *value* for *key* under *stamp*, clearing wholesale when full."""
        with self._lock:
            if len(self._entries) >= self._max_entries:
                self._entries.clear()
            self._entries[key] = (stamp, value)

    def clear(self) -> None:
        """Drop every entry."""
        with self._lock:
            self._entries.clear()


#: Process-wide default; pass ``cache=`` to memoize into an isolated store.
DEFAULT_CACHE = StampCache(name="default")


def approx_size(value: object, _seen: set[int] | None = None) -> int:
    """Rough byte size of *value*: containers recursed, other objects shallow."""
    seen = _seen if _seen is not None else set()
    if id(value) in seen:
        return 0
    seen.add(id(value))
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(approx_size(k, seen) + approx_size(v, seen) for k, v in value.items())
    elif isinstance(value, (list, tuple, set, frozenset)):
        size += sum(approx_size(item, seen) for item in value)
    return size


def file_stamp(path: Path) -> tuple[int, int] | None:
    """Identity of *path*'s contents on disk, or None when it is not a file."""
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def memoized_by_stamp(
    key: str, stamp: tuple, compute: Callable[[], T | None], *, cache: StampCache | None = None,
) -> T | None:
    """``compute()`` for *key*, reused while *stamp* is unchanged.

    A None result is passed through without memoizing it, so a transient
    failure never freezes an empty result. Callers that hand the result out
    must copy it: the memo keeps the same object.
    """
    store = cache if cache is not None else DEFAULT_CACHE
    hit = store.get(key, stamp)
    if hit is not None:
        return hit  # type: ignore[return-value]
    value = compute()
    if value is None:
        return None
    store.put(key, stamp, value)
    return value
