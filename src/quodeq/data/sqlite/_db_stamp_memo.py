"""In-process memo keyed by a SQLite database's on-disk stamp.

A read that only depends on a database's contents can be reused while the
file has not changed. The stamp is the main file's mtime and size plus the
WAL's: a live writer commits into ``<db>-wal`` and the main file only moves
at checkpoint, so the WAL is part of the identity. The stamp is taken before
the read, so a write racing the read only costs one extra recompute.

The store is ``shared.stamp_memo.StampCache``; this module only knows how
to stamp a SQLite database.
"""
from __future__ import annotations

import stat as _stat
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from quodeq.shared.stamp_memo import DEFAULT_CACHE, StampCache, file_stamp, memoized_by_stamp

T = TypeVar("T")

#: The store and the memo live in ``shared.stamp_memo``; these aliases keep
#: the names this module's callers and tests use.
_StampCache = StampCache
_DEFAULT_CACHE = DEFAULT_CACHE


def db_stamp(db_path: Path) -> tuple | None:
    """Identity of *db_path*'s contents on disk, or None when it is not a file."""
    try:
        st = db_path.stat()
    except OSError:
        return None
    if not _stat.S_ISREG(st.st_mode):
        return None
    wal_part = file_stamp(db_path.with_name(db_path.name + "-wal"))
    return (st.st_mtime_ns, st.st_size, wal_part)


def memoized_by_db_stamp(db_path: Path, compute: Callable[[], T | None],
                         cache: StampCache | None = None) -> T | None:
    """``compute()`` for *db_path*, reused while the database is unchanged.

    Returns None without calling *compute* when there is no database. See
    ``shared.stamp_memo.memoized_by_stamp`` for the None and copy rules.
    """
    stamp = db_stamp(db_path)
    if stamp is None:
        return None
    return memoized_by_stamp(str(db_path), stamp, compute, cache=cache)
