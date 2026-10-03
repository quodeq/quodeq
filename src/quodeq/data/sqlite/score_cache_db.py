"""Score-cache DB plumbing: path resolution, schema, and corrupt-db repair.

Disposable/best-effort by design: a corrupt or older-schema db is unlinked and
rebuilt instead of surfacing an error to the caller.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator

from quodeq.data.sqlite.constants import SQLITE_BUSY_TIMEOUT_MS
from quodeq.data.sqlite._score_cache_epoch import CACHE_WRITER_EPOCH
from quodeq.data.sqlite.score_cache_schema import (
    SCHEMA, ensure_run_scalars_columns, sync_cache_meta,
)
from quodeq.shared.env import get_score_cache_path

_logger = logging.getLogger(__name__)

# Shared-root isolation seam: when serving read endpoints from a
# second (shared) clone, the score cache must not mix rows with the local
# clone's cache. Unset (None) in every normal code path, so the default
# behavior below is byte-identical to before this seam existed.
_CACHE_PATH_OVERRIDE: ContextVar[str | None] = ContextVar(
    "score_cache_path_override", default=None
)


@contextmanager
def score_cache_path_override(path: str | Path) -> Iterator[None]:
    """Route score-cache reads/writes to *path* instead of the default DB.

    Active only for the duration of the ``with`` block (and any code it
    calls, via contextvars' task-local propagation); always restored,
    including when the block raises.
    """
    token = _CACHE_PATH_OVERRIDE.set(str(path))
    try:
        yield
    finally:
        _CACHE_PATH_OVERRIDE.reset(token)


def _init(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        conn.executescript(SCHEMA)
        conn.commit()
        ensure_run_scalars_columns(conn)
        sync_cache_meta(conn)
    except sqlite3.DatabaseError:
        # Close before re-raising so the caller's rebuild path can unlink the
        # file with no open handle (Windows raises PermissionError otherwise).
        conn.close()
        raise
    return conn


# Serializes _init (and the corrupt-db rebuild). Concurrent first-opens of a
# fresh DB race the schema DDL; the loser's lock error is indistinguishable
# from corruption here, so the rebuild path would unlink the file out from
# under the winner's live WAL connection (observed as a SIGBUS on the mmap'd
# -shm). Only open/rebuild is serialized — yielded connections stay concurrent.
_OPEN_LOCK = threading.Lock()

# Files this process has fully initialized, keyed by
# (path, st_dev, st_ino, CACHE_WRITER_EPOCH). A hit skips the DDL, the commit
# and the epoch purge. The inode is in the key so a deleted and recreated file
# misses; path plus epoch alone would skip the DDL on a fresh empty file.
_INITIALIZED: set[tuple[str, int, int, str]] = set()


def _identity(path: Path) -> tuple[str, int, int, str] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (str(path), st.st_dev, st.st_ino, CACHE_WRITER_EPOCH)


def _connect_initialized(path: Path) -> sqlite3.Connection:
    """Fast path for a file already initialized here: connect, set the busy
    timeout, and prove the schema is still there with one single-row read
    (an inode can be reused by a brand-new file)."""
    conn = sqlite3.connect(path)
    try:
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        row = conn.execute(
            "SELECT value FROM cache_meta WHERE key='writer_epoch'"
        ).fetchone()
    except sqlite3.DatabaseError:
        conn.close()
        raise
    if row is None or row[0] != CACHE_WRITER_EPOCH:
        conn.close()
        raise sqlite3.DatabaseError("score cache not initialized for this epoch")
    return conn


def _open_locked(path: Path) -> sqlite3.Connection:
    """Open *path*, running the full init only on a memo miss. Caller holds _OPEN_LOCK."""
    ident = _identity(path)
    if ident in _INITIALIZED:
        try:
            return _connect_initialized(path)
        except sqlite3.DatabaseError:
            _INITIALIZED.discard(ident)
    try:
        conn = _init(path)
    except sqlite3.OperationalError:
        # Lock contention, not corruption -- another connection is mid-write.
        # Propagate so the caller can retry; deleting the file here would
        # destroy a live, healthy database out from under its writer.
        raise
    except sqlite3.DatabaseError:
        _logger.warning("score cache at %s unreadable; rebuilding", path)
        path.unlink(missing_ok=True)
        conn = _init(path)
    ident = _identity(path)
    if ident is not None:
        _INITIALIZED.add(ident)
    return conn


def _forget(path: Path) -> None:
    """Drop every memo entry for *path*, so its next open runs the full init."""
    key = str(path)
    with _OPEN_LOCK:
        _INITIALIZED.difference_update({i for i in _INITIALIZED if i[0] == key})


# A request-scoped connection: while a ``score_cache_session`` is active,
# every ``open_score_cache`` inside it yields this connection instead of
# opening its own. Unset in every normal code path.
_SESSION_CONN: ContextVar[sqlite3.Connection | None] = ContextVar("score_cache_session", default=None)


def _resolve_path() -> Path:
    override = _CACHE_PATH_OVERRIDE.get()
    path = Path(override) if override else Path(get_score_cache_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def _connection(path: Path) -> Iterator[sqlite3.Connection]:
    with _OPEN_LOCK:
        conn = _open_locked(path)
    try:
        yield conn
    except sqlite3.DatabaseError:
        _forget(path)
        raise
    finally:
        conn.close()


@contextmanager
def open_score_cache() -> Iterator[sqlite3.Connection]:
    """Open the score cache DB (WAL). Rebuilds from scratch if corrupt/older-schema.

    The first open of a file in this process runs the full init; later opens
    of the same file only connect. A DatabaseError raised inside the block
    forgets the file, so the next open runs the full init again. Inside a
    ``score_cache_session`` the session's connection is yielded instead and
    stays open for the session.
    """
    shared = _SESSION_CONN.get()
    if shared is not None:
        yield shared
        return
    with _connection(_resolve_path()) as conn:
        yield conn


@contextmanager
def score_cache_session() -> Iterator[None]:
    """One connection for every score-cache access in the block.

    For requests that touch many projects (the fleet compare): the rows,
    versions and writes of every project go through a single open instead
    of one per read. Sessions do not nest; an inner session reuses the
    outer connection.
    """
    if _SESSION_CONN.get() is not None:
        yield
        return
    with _connection(_resolve_path()) as conn:
        token = _SESSION_CONN.set(conn)
        try:
            yield
        finally:
            _SESSION_CONN.reset(token)
