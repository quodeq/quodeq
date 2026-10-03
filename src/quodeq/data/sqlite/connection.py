"""Connection context manager for evaluation.db.

Sets WAL mode, foreign keys, and a busy-timeout that tolerates concurrent
sibling MCP server processes (mirrors the behavior of the existing JSONL
write path which relies on POSIX flock).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from quodeq.data.sqlite._db_stamp_memo import db_stamp
from quodeq.data.sqlite._migrations import apply_evaluation_schema
from quodeq.data.sqlite.constants import SQLITE_BUSY_TIMEOUT_MS
from quodeq.data.sqlite.errors import SqliteStoreUnreadableError, as_store_error
from quodeq.shared import request_metrics

EVALUATION_DB_FILENAME = "evaluation.db"


def evaluation_db_stamp(run_dir: Path) -> tuple | None:
    """Identity of the run database's contents on disk (main file and WAL),
    or None when the run has none. For memos that hold while it is unchanged."""
    return db_stamp(run_dir / EVALUATION_DB_FILENAME)


def _configure(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")


@contextmanager
def open_evaluation_db(run_dir: Path) -> Iterator[sqlite3.Connection]:
    """Open (creating if needed) the run's evaluation.db with the schema applied.

    Creates *run_dir* and closes the connection on the way out. Connect and IO
    failures surface as ``RuntimeError`` naming the path; schema-version
    mismatches and corruption surface as ``StoreUnreadableError`` (still a
    ``sqlite3.DatabaseError``) so readers can fall back to the filesystem.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / EVALUATION_DB_FILENAME
    conn: sqlite3.Connection | None = None
    try:
        try:
            request_metrics.count("db_opens")
            conn = sqlite3.connect(path)
            _configure(conn)
            apply_evaluation_schema(conn)
            conn.commit()
        except sqlite3.OperationalError as exc:
            # Connect/IO-level failures (locked or missing file, disk I/O error):
            # give callers a clear, run-scoped message instead of a bare sqlite3
            # error with no path context.
            raise RuntimeError(f"Could not open evaluation database at {path}: {exc}") from exc
        except SqliteStoreUnreadableError:
            # A schema-version mismatch already is the boundary error.
            raise
        except sqlite3.DatabaseError as exc:
            # Generic corruption ("file is not a database") becomes the
            # boundary's unreadable-store error, which is still a
            # sqlite3.DatabaseError: readers (dashboard/scores/findings
            # queries) catch either type to degrade gracefully to
            # filesystem-based data. Wrapping in RuntimeError would break
            # that fallback.
            raise as_store_error(exc) from exc
        except sqlite3.Error as exc:
            raise RuntimeError(f"Could not open evaluation database at {path}: {exc}") from exc
        try:
            yield conn
        except SqliteStoreUnreadableError:
            raise
        except sqlite3.DatabaseError as exc:
            # A malformed image can surface on the first query rather than
            # at connect time; it gets the same boundary error.
            raise as_store_error(exc) from exc
    finally:
        # Guards both setup failures (conn may or may not have been created)
        # and the normal yield path -- conn is only ever left open here if
        # sqlite3.connect() itself never returned one.
        if conn is not None:
            conn.close()
