"""Content index over cache entries.

A sqlite sidecar at ``<results root>/.index.db`` mapping
``(content_hash, dimension, params_hash)`` to the keys of entries that were
written with those inputs. It exists so a classify miss can ask "was this
exact content already evaluated for this dimension under another path?"
(a directory move) without walking 100k entry files.

The index is derivable from the entries and is never authoritative: callers
verify a row against the entry it points to. Every method is best-effort. A
sqlite or IO failure logs at debug and reports nothing, so the cache degrades
to today's miss behavior rather than breaking a scan. A corrupt file is
deleted and recreated on the next open; ``ensure_cache_ready`` rebuilds the
rows.

One connection per instance, guarded by a lock (``check_same_thread=False``
because the dimension runner's persist watcher writes from its own thread).
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

_logger = logging.getLogger(__name__)

INDEX_FILENAME = ".index.db"
_BUSY_TIMEOUT_MS = 5000
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entries (
  key          TEXT PRIMARY KEY,
  content_hash TEXT NOT NULL,
  dimension    TEXT NOT NULL,
  params_hash  TEXT NOT NULL DEFAULT '',
  file_path    TEXT NOT NULL,
  created_at   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_entries_content
  ON entries(content_hash, dimension, params_hash);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""
_BUILT_KEY = "built_for_schema"


@dataclass(frozen=True)
class IndexRow:
    key: str
    file_path: str
    created_at: str


class ContentIndex:
    """Best-effort sqlite index over cache entries. See module docstring."""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._broken = False

    # -- connection -------------------------------------------------------

    def _open(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._path), check_same_thread=False)
        try:
            conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA_SQL)
        except sqlite3.Error:
            conn.close()
            raise
        return conn

    def _connect(self) -> sqlite3.Connection | None:
        """Return the connection, opening it lazily. None when unusable."""
        if self._conn is not None:
            return self._conn
        if self._broken:
            return None
        try:
            self._conn = self._open()
        except sqlite3.DatabaseError as exc:
            # "file is not a database" and friends: drop the corrupt file and
            # try once more. The rows are rebuilt by ensure_cache_ready.
            _logger.debug("content index corrupt at %s (%s); recreating", self._path, exc)
            try:
                self._path.unlink(missing_ok=True)
                self._conn = self._open()
            except (sqlite3.Error, OSError) as exc2:
                _logger.debug("content index unavailable at %s: %s", self._path, exc2)
                self._broken = True
                return None
        except (sqlite3.Error, OSError) as exc:
            _logger.debug("content index unavailable at %s: %s", self._path, exc)
            self._broken = True
            return None
        return self._conn

    def close(self) -> None:
        """Close the connection. The next operation reopens it."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except sqlite3.Error:
                    pass
                self._conn = None

    # -- writes -----------------------------------------------------------

    def record(
        self, key: str, *, content_hash: str, dimension: str, params_hash: str,
        file_path: str, created_at: str,
    ) -> None:
        self.record_many([(key, content_hash, dimension, params_hash, file_path, created_at)])

    def record_many(self, rows: Iterable[tuple[str, str, str, str, str, str]]) -> None:
        """Insert or replace rows ``(key, content_hash, dimension, params_hash,
        file_path, created_at)`` in one transaction. Rows with a blank content
        hash are skipped: nothing can be adopted from them."""
        payload = [r for r in rows if r[1]]
        if not payload:
            return
        with self._lock:
            conn = self._connect()
            if conn is None:
                return
            try:
                with conn:
                    conn.executemany(
                        "INSERT OR REPLACE INTO entries"
                        "(key, content_hash, dimension, params_hash, file_path, created_at)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        payload,
                    )
            except sqlite3.Error as exc:
                _logger.debug("content index write failed: %s", exc)

    def forget(self, key: str) -> None:
        with self._lock:
            conn = self._connect()
            if conn is None:
                return
            try:
                with conn:
                    conn.execute("DELETE FROM entries WHERE key = ?", (key,))
            except sqlite3.Error as exc:
                _logger.debug("content index delete failed: %s", exc)

    # -- reads ------------------------------------------------------------

    def find(
        self, content_hash: str, dimension: str, params_hash: str, *, limit: int = 50,
    ) -> list[IndexRow]:
        """Rows with these inputs, newest first. Empty on any failure."""
        if not content_hash:
            return []
        with self._lock:
            conn = self._connect()
            if conn is None:
                return []
            try:
                cur = conn.execute(
                    "SELECT key, file_path, created_at FROM entries"
                    " WHERE content_hash = ? AND dimension = ? AND params_hash = ?"
                    " ORDER BY created_at DESC LIMIT ?",
                    (content_hash, dimension, params_hash, limit),
                )
                return [IndexRow(key=k, file_path=p, created_at=c) for k, p, c in cur.fetchall()]
            except sqlite3.Error as exc:
                _logger.debug("content index read failed: %s", exc)
                return []

    def built_for_schema(self) -> int | None:
        """The schema the rows were last built for, or None when unknown."""
        with self._lock:
            conn = self._connect()
            if conn is None:
                return None
            try:
                row = conn.execute("SELECT v FROM meta WHERE k = ?", (_BUILT_KEY,)).fetchone()
            except sqlite3.Error:
                return None
        if row is None:
            return None
        try:
            return int(row[0])
        except (TypeError, ValueError):
            return None

    def mark_built(self, schema: int) -> None:
        with self._lock:
            conn = self._connect()
            if conn is None:
                return
            try:
                with conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO meta(k, v) VALUES (?, ?)",
                        (_BUILT_KEY, str(schema)),
                    )
            except sqlite3.Error as exc:
                _logger.debug("content index meta write failed: %s", exc)
