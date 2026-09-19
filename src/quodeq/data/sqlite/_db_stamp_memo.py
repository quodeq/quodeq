"""In-process memo keyed by a SQLite database's on-disk stamp.

A read that only depends on a database's contents can be reused while the
file has not changed. The stamp is the main file's mtime and size plus the
WAL's: a live writer commits into ``<db>-wal`` and the main file only moves
at checkpoint, so the WAL is part of the identity. The stamp is taken before
the read, so a write racing the read only costs one extra recompute.

Bounded by a wholesale clear rather than an LRU: the set of databases a
process visits is small and stable, so the bound only guards against
unbounded growth.
"""
from __future__ import annotations

import stat as _stat
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")

_MEMO_MAX = 4096


class _StampCache:
    """Stamp-keyed store behind the memo, bounded by a wholesale clear."""

    def __init__(self, max_entries: int = _MEMO_MAX) -> None:
        self._entries: dict[str, tuple[tuple, object]] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries

    def get(self, key: str, stamp: tuple) -> object | None:
        """The value stored for *key* under *stamp*, or None when it is not current."""
        with self._lock:
            hit = self._entries.get(key)
        if hit is None or hit[0] != stamp:
            return None
        return hit[1]

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
_DEFAULT_CACHE = _StampCache()


def db_stamp(db_path: Path) -> tuple | None:
    """Identity of *db_path*'s contents on disk, or None when it is not a file."""
    try:
        st = db_path.stat()
    except OSError:
        return None
    if not _stat.S_ISREG(st.st_mode):
        return None
    wal = db_path.with_name(db_path.name + "-wal")
    try:
        wst = wal.stat()
        wal_part: tuple[int, int] | None = (wst.st_mtime_ns, wst.st_size)
    except OSError:
        wal_part = None
    return (st.st_mtime_ns, st.st_size, wal_part)


def memoized_by_db_stamp(db_path: Path, compute: Callable[[], T | None],
                         cache: _StampCache | None = None) -> T | None:
    """``compute()`` for *db_path*, reused while the database is unchanged.

    Returns None without calling *compute* when there is no database, and
    passes a None result (an unreadable database) through without memoizing
    it, so a transient failure never freezes an empty result. Callers that
    hand the result out must copy it: the memo keeps the same object.
    *cache* overrides the process-wide store (``_DEFAULT_CACHE``); call
    ``clear()`` on it to drop what it holds.
    """
    store = cache if cache is not None else _DEFAULT_CACHE
    stamp = db_stamp(db_path)
    if stamp is None:
        return None
    key = str(db_path)
    hit = store.get(key, stamp)
    if hit is not None:
        # a None value is never stored, so a hit is always a real result
        return hit  # type: ignore[return-value]
    value = compute()
    if value is None:
        return None
    store.put(key, stamp, value)
    return value
