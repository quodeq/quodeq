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

from quodeq.data.sqlite._migrations import apply_evaluation_schema

EVALUATION_DB_FILENAME = "evaluation.db"
_BUSY_TIMEOUT_MS = 5000


def _configure(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")


@contextmanager
def open_evaluation_db(run_dir: Path) -> Iterator[sqlite3.Connection]:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / EVALUATION_DB_FILENAME
    conn: sqlite3.Connection | None = None
    try:
        try:
            conn = sqlite3.connect(path)
            _configure(conn)
            apply_evaluation_schema(conn)
            conn.commit()
        except sqlite3.OperationalError as exc:
            # Connect/IO-level failures (locked or missing file, disk I/O error):
            # give callers a clear, run-scoped message instead of a bare sqlite3
            # error with no path context.
            raise RuntimeError(f"Could not open evaluation database at {path}: {exc}") from exc
        except sqlite3.DatabaseError:
            # Schema-version mismatches (SchemaVersionError) and generic
            # corruption ("file is not a database") deliberately stay
            # sqlite3.DatabaseError subclasses/instances -- existing readers
            # (dashboard/scores/findings queries) catch that type to degrade
            # gracefully to filesystem-based data. Wrapping these in RuntimeError
            # would break that fallback, so let them propagate unchanged.
            raise
        except sqlite3.Error as exc:
            raise RuntimeError(f"Could not open evaluation database at {path}: {exc}") from exc
        yield conn
    finally:
        # Guards both setup failures (conn may or may not have been created)
        # and the normal yield path -- conn is only ever left open here if
        # sqlite3.connect() itself never returned one.
        if conn is not None:
            conn.close()
