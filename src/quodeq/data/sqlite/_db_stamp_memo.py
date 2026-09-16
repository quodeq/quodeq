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

import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")

_MEMO: dict[str, tuple[tuple, object]] = {}
_LOCK = threading.Lock()
_MEMO_MAX = 4096


def db_stamp(db_path: Path) -> tuple | None:
    """Identity of *db_path*'s contents on disk, or None when it is not a file."""
    try:
        st = db_path.stat()
    except OSError:
        return None
    if not db_path.is_file():
        return None
    wal = db_path.with_name(db_path.name + "-wal")
    try:
        wst = wal.stat()
        wal_part: tuple[int, int] | None = (wst.st_mtime_ns, wst.st_size)
    except OSError:
        wal_part = None
    return (st.st_mtime_ns, st.st_size, wal_part)


def memoized_by_db_stamp(db_path: Path, compute: Callable[[], T | None]) -> T | None:
    """``compute()`` for *db_path*, reused while the database is unchanged.

    Returns None without calling *compute* when there is no database, and
    passes a None result (an unreadable database) through without memoizing
    it, so a transient failure never freezes an empty result. Callers that
    hand the result out must copy it: the memo keeps the same object.
    """
    stamp = db_stamp(db_path)
    if stamp is None:
        return None
    key = str(db_path)
    with _LOCK:
        hit = _MEMO.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1]  # type: ignore[return-value]
    value = compute()
    if value is None:
        return None
    with _LOCK:
        if len(_MEMO) >= _MEMO_MAX:
            _MEMO.clear()
        _MEMO[key] = (stamp, value)
    return value
