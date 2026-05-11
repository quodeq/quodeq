"""SQLite cache wrapper for the symbol index."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from quodeq.resolver.schema import DDL, SCHEMA_VERSION


class IndexCache:
    """Thin wrapper around a SQLite connection for the resolver's symbol index."""

    def __init__(self, db_path: Path, parser_version: str | None = None) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(DDL)
        self.set_meta("schema_version", str(SCHEMA_VERSION))
        if parser_version is not None:
            self.set_meta("parser_version", parser_version)

    def list_tables(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
