"""Per-project vector store for dismissed-finding embeddings.

Derived, rebuildable state (like index.db / score_cache.db) living at
``<evaluations_dir>/<project>/precedent_vectors.db`` next to actions.jsonl.
Deliberately NOT inside evaluation.db: no shared migration chain, no
SCHEMA_VERSION coupling, and only precedent code ever opens it.

Concurrency: up to N agent processes open this DB at scan start. Rules:
- busy_timeout is set FIRST (before any other pragma) so contention waits
  instead of erroring (score_cache sets WAL first — do not copy that).
- Lock contention degrades (yields None); ONLY genuine corruption rebuilds.
- All vector writes are INSERT OR IGNORE and re-verify the model stamp
  inside the same transaction, so mixed-model vectors are never served.
"""
from __future__ import annotations

import logging
import sqlite3
import struct
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

_logger = logging.getLogger(__name__)

DB_NAME = "precedent_vectors.db"
_BUSY_TIMEOUT_MS = 5000
_CLAIM_STALE_S = 120.0
_CORRUPTION_MARKERS = ("file is not a database", "database disk image is malformed")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vectors (
  fingerprint TEXT PRIMARY KEY,
  vector BLOB NOT NULL,
  created_at TEXT NOT NULL
);
"""


def _is_corruption(exc: sqlite3.DatabaseError) -> bool:
    msg = str(exc).lower()
    if any(marker in msg for marker in _CORRUPTION_MARKERS):
        return True
    # OperationalError covers locks/timeouts/IO-busy: never treat as corrupt.
    return not isinstance(exc, sqlite3.OperationalError)


def _init(path: Path, busy_timeout_ms: int) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    try:
        conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(_SCHEMA)
        conn.commit()
        # Verify write access to detect lock contention early (e.g., in WAL mode).
        conn.execute("BEGIN")
        conn.execute("INSERT OR IGNORE INTO meta VALUES ('__placeholder__', '__1')")
        conn.rollback()
    except sqlite3.DatabaseError:
        # Close before re-raising so a rebuild can unlink with no open handle
        # (Windows raises PermissionError otherwise).
        conn.close()
        raise
    return conn


def _ensure_model(conn: sqlite3.Connection, model: str) -> None:
    row = conn.execute(
        "SELECT value FROM meta WHERE key = 'embedding_model'"
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT OR IGNORE INTO meta VALUES ('embedding_model', ?)", (model,)
        )
        conn.commit()
    elif row[0] != model:
        _logger.info(
            "Embedding model changed (%s -> %s): wiping precedent vectors", row[0], model
        )
        conn.execute("DELETE FROM vectors")
        conn.execute("DELETE FROM meta")
        conn.execute("INSERT INTO meta VALUES ('embedding_model', ?)", (model,))
        conn.commit()


@contextmanager
def open_vector_store(
    project_dir: Path, model: str, *, busy_timeout_ms: int = _BUSY_TIMEOUT_MS,
) -> Iterator[sqlite3.Connection | None]:
    """Yield a model-validated connection, or None when the store is unusable.

    None means "degrade to no semantic tier this load" — never an exception.
    """
    path = project_dir / DB_NAME
    conn: sqlite3.Connection | None = None
    try:
        try:
            conn = _init(path, busy_timeout_ms)
        except sqlite3.DatabaseError as exc:
            if not _is_corruption(exc):
                _logger.warning("Precedent vector store busy/unreadable: %s", exc)
                yield None
                return
            _logger.warning("Precedent vector store corrupt; rebuilding: %s", exc)
            try:
                path.unlink(missing_ok=True)
            except PermissionError:
                # Windows: another process holds the file open. Degrade.
                yield None
                return
            conn = _init(path, busy_timeout_ms)
        _ensure_model(conn, model)
        yield conn
    except sqlite3.DatabaseError as exc:
        _logger.warning("Precedent vector store error: %s", exc)
        yield None
    finally:
        if conn is not None:
            conn.close()


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


def stored_fingerprints(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT fingerprint FROM vectors")}


def insert_vectors(
    conn: sqlite3.Connection, model: str, items: list[tuple[str, list[float]]],
) -> bool:
    """INSERT OR IGNORE *items*; abort (False) if the model stamp changed."""
    if not items:
        return True
    dims = len(items[0][1])
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'embedding_model'"
        ).fetchone()
        if row is None or row[0] != model:
            conn.rollback()
            return False
        conn.execute("INSERT OR IGNORE INTO meta VALUES ('dims', ?)", (str(dims),))
        conn.executemany(
            "INSERT OR IGNORE INTO vectors VALUES (?, ?, ?)",
            [(fp, _pack(vec), now) for fp, vec in items],
        )
        conn.commit()
        return True
    except sqlite3.DatabaseError as exc:
        _logger.warning("Precedent vector insert failed: %s", exc)
        try:
            conn.rollback()
        except sqlite3.DatabaseError:
            pass
        return False


def load_vectors(conn: sqlite3.Connection) -> list[tuple[str, list[float]]]:
    """Load all vectors whose byte length matches the stamped dims."""
    row = conn.execute("SELECT value FROM meta WHERE key = 'dims'").fetchone()
    if row is None:
        return []
    expected = int(row[0]) * 4
    out: list[tuple[str, list[float]]] = []
    for fp, blob in conn.execute("SELECT fingerprint, vector FROM vectors"):
        if len(blob) == expected:
            out.append((fp, _unpack(blob)))
    return out


def try_claim_backfill(conn: sqlite3.Connection) -> bool:
    """Advisory single-writer claim for the backfill; stale claims are stolen."""
    now = time.time()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO meta VALUES ('backfill_claim', ?)", (str(now),)
        )
        if cur.rowcount == 1:
            conn.commit()
            return True
        cur = conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'backfill_claim' "
            "AND CAST(value AS REAL) < ?",
            (str(now), now - _CLAIM_STALE_S),
        )
        conn.commit()
        return cur.rowcount == 1
    except sqlite3.DatabaseError:
        return False


def release_backfill_claim(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("DELETE FROM meta WHERE key = 'backfill_claim'")
        conn.commit()
    except sqlite3.DatabaseError:
        pass
