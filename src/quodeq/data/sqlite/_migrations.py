"""Apply schema DDL to a fresh SQLite connection. Refuse newer-version DBs."""
from __future__ import annotations

import sqlite3

from quodeq.data.sqlite._schema import EVALUATION_DDL, SCHEMA_VERSION


class SchemaVersionError(RuntimeError):
    """Raised when the on-disk DB has a newer schema than this binary supports."""


def _current_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


# Incremental upgrades from version N to N+1. Each function takes a connection
# already at version N; the caller bumps PRAGMA user_version to N+1 afterwards.
def _upgrade_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Add per-finding confidence column (default 100 = full confidence)."""
    conn.execute("ALTER TABLE findings ADD COLUMN confidence INTEGER NOT NULL DEFAULT 100")


def _upgrade_v2_to_v3(conn: sqlite3.Connection) -> None:
    """Add principle_grades table for per-principle scoring."""
    conn.executescript("""
        CREATE TABLE principle_grades (
            dimension        TEXT NOT NULL,
            principle_id     TEXT NOT NULL,
            score            REAL,
            grade            TEXT,
            finding_count    INTEGER NOT NULL DEFAULT 0,
            dismissed_count  INTEGER NOT NULL DEFAULT 0,
            completed_at     TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (dimension, principle_id)
        );

        CREATE INDEX idx_principle_grades_dimension ON principle_grades(dimension);
    """)


_UPGRADES = {
    1: _upgrade_v1_to_v2,
    2: _upgrade_v2_to_v3,
}


def apply_evaluation_schema(conn: sqlite3.Connection) -> None:
    version = _current_version(conn)
    if version == SCHEMA_VERSION:
        return
    if version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"evaluation.db has schema version {version}, "
            f"this binary supports {SCHEMA_VERSION}",
        )
    if version == 0:
        # Fresh DB: apply the latest DDL (its leading PRAGMA sets user_version).
        conn.executescript(EVALUATION_DDL)
        return
    # Incremental upgrade path: walk N -> N+1 -> ... -> SCHEMA_VERSION.
    while version < SCHEMA_VERSION:
        upgrade = _UPGRADES.get(version)
        if upgrade is None:
            raise SchemaVersionError(
                f"missing upgrade path from schema version {version} "
                f"(target: {SCHEMA_VERSION})",
            )
        upgrade(conn)
        version += 1
        conn.execute(f"PRAGMA user_version = {version}")
