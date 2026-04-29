"""Apply schema DDL to a fresh SQLite connection. Refuse newer-version DBs."""
from __future__ import annotations

import sqlite3

from quodeq.data.sqlite._schema import EVALUATION_DDL, INDEX_DDL, SCHEMA_VERSION


class SchemaVersionError(RuntimeError):
    """Raised when the on-disk DB has a newer schema than this binary supports."""


def _current_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def apply_evaluation_schema(conn: sqlite3.Connection) -> None:
    version = _current_version(conn)
    if version == SCHEMA_VERSION:
        return
    if version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"evaluation.db has schema version {version}, "
            f"this binary supports {SCHEMA_VERSION}",
        )
    if version != 0:
        raise SchemaVersionError(
            f"unexpected evaluation.db schema version {version} (expected 0 or {SCHEMA_VERSION})",
        )
    conn.executescript(EVALUATION_DDL)


def apply_index_schema(conn: sqlite3.Connection) -> None:
    version = _current_version(conn)
    if version == SCHEMA_VERSION:
        return
    if version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"index.db has schema version {version}, "
            f"this binary supports {SCHEMA_VERSION}",
        )
    if version != 0:
        raise SchemaVersionError(
            f"unexpected index.db schema version {version} (expected 0 or {SCHEMA_VERSION})",
        )
    conn.executescript(INDEX_DDL)
