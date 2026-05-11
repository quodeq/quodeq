"""SQLite cache wrapper for the symbol index."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from quodeq.resolver.schema import DDL, SCHEMA_VERSION


class IndexCache:
    """Thin wrapper around a SQLite connection for the resolver's symbol index.

    Thread safety: a single ``threading.Lock`` serialises all access to
    ``self.conn``.  With WAL mode enabled SQLite allows concurrent readers at
    the storage level, but Python's ``sqlite3.Connection`` is not thread-safe
    by itself.  Callers that share an ``IndexCache`` across threads (e.g. the
    verifier service reusing a cached ``Resolver``) rely on this lock rather
    than managing synchronisation themselves.
    """

    def __init__(self, db_path: Path, parser_version: str | None = None) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.executescript(DDL)
        self.set_meta("schema_version", str(SCHEMA_VERSION))
        if parser_version is not None:
            self.set_meta("parser_version", parser_version)

    def execute(self, sql: str, params: tuple = ()) -> list:
        """Execute a read query under the connection lock and return all rows."""
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    def list_tables(self) -> list[str]:
        rows = self.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [r["name"] for r in rows]

    def get_meta(self, key: str) -> str | None:
        with self._lock:
            row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self.conn.commit()

    def close(self) -> None:
        with self._lock:
            self.conn.close()
