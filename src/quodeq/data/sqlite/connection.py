"""Connection context managers for evaluation.db and index.db.

Sets WAL mode, foreign keys, and a busy-timeout that tolerates concurrent
sibling MCP server processes (mirrors the behavior of the existing JSONL
write path which relies on POSIX flock).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from quodeq.data.sqlite._migrations import apply_evaluation_schema, apply_index_schema

EVALUATION_DB_FILENAME = "evaluation.db"
INDEX_DB_FILENAME = "index.db"
_BUSY_TIMEOUT_MS = 5000


def _configure(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")


@contextmanager
def open_evaluation_db(run_dir: Path) -> Iterator[sqlite3.Connection]:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / EVALUATION_DB_FILENAME
    conn = sqlite3.connect(path)
    try:
        _configure(conn)
        apply_evaluation_schema(conn)
        conn.commit()
        yield conn
    finally:
        conn.close()


@contextmanager
def open_index_db(quodeq_root: Path) -> Iterator[sqlite3.Connection]:
    quodeq_root.mkdir(parents=True, exist_ok=True)
    path = quodeq_root / INDEX_DB_FILENAME
    conn = sqlite3.connect(path)
    try:
        _configure(conn)
        apply_index_schema(conn)
        conn.commit()
        yield conn
    finally:
        conn.close()
