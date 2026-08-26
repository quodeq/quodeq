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

from quodeq.services._score_cache_epoch import CACHE_WRITER_EPOCH
from quodeq.shared._env import get_score_cache_path

_logger = logging.getLogger(__name__)
_BUSY_TIMEOUT_MS = 5000

# Shared-root isolation seam (Phase 2): when serving read endpoints from a
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


_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS run_scalars ("
    " project TEXT NOT NULL, run_id TEXT NOT NULL, version TEXT NOT NULL,"
    " dimension TEXT NOT NULL, overall_score TEXT, overall_grade TEXT,"
    " updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
    " PRIMARY KEY (project, run_id, dimension, version));"
    "CREATE INDEX IF NOT EXISTS idx_run_scalars_lookup ON run_scalars(project, version);"
    "CREATE TABLE IF NOT EXISTS accumulated_cache ("
    " project TEXT NOT NULL, version TEXT NOT NULL, payload TEXT NOT NULL,"
    " updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
    " PRIMARY KEY (project, version));"
    "CREATE TABLE IF NOT EXISTS project_summary_cache ("
    " project TEXT PRIMARY KEY, version TEXT NOT NULL, payload TEXT NOT NULL);"
    "CREATE TABLE IF NOT EXISTS run_keys ("
    " project TEXT NOT NULL, run_id TEXT NOT NULL,"
    " dismiss_keys TEXT NOT NULL, class_keys TEXT NOT NULL,"
    " PRIMARY KEY (project, run_id));"
    "CREATE TABLE IF NOT EXISTS cache_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
)


def _purge_run_keys_on_epoch_change(conn: sqlite3.Connection) -> None:
    """One-time purge of the non-version-keyed run_keys table on epoch bump.

    ``run_scalars`` / ``accumulated_cache`` / ``project_summary_cache`` embed the
    epoch in their version hash and self-invalidate, but ``run_keys`` rows are not
    version-keyed, so a partial snapshot persisted by a prior writer would survive
    a bump and stay frozen. Clearing the table once forces a fresh read.
    """
    try:
        row = conn.execute(
            "SELECT value FROM cache_meta WHERE key='writer_epoch'"
        ).fetchone()
        if row is not None and row[0] == CACHE_WRITER_EPOCH:
            return
        conn.execute("DELETE FROM run_keys")
        conn.execute(
            "INSERT OR REPLACE INTO cache_meta (key, value) VALUES ('writer_epoch', ?)",
            (CACHE_WRITER_EPOCH,),
        )
        conn.commit()
    except sqlite3.Error:
        _logger.warning("run_keys epoch purge failed", exc_info=True)


def _init(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        conn.executescript(_SCHEMA)
        conn.commit()
        _purge_run_keys_on_epoch_change(conn)
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


@contextmanager
def open_score_cache() -> Iterator[sqlite3.Connection]:
    """Open the score cache DB (WAL). Rebuilds from scratch if corrupt/older-schema."""
    override = _CACHE_PATH_OVERRIDE.get()
    path = Path(override) if override else Path(get_score_cache_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with _OPEN_LOCK:
        try:
            conn = _init(path)
        except sqlite3.DatabaseError:
            _logger.warning("score cache at %s unreadable; rebuilding", path)
            path.unlink(missing_ok=True)
            conn = _init(path)
    try:
        yield conn
    finally:
        conn.close()
