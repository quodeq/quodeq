"""dimension_scores has an exit_reason column on fresh and upgraded DBs."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from quodeq.data.sqlite._migrations import apply_evaluation_schema
from quodeq.data.sqlite._schema import SCHEMA_VERSION


def test_fresh_db_dimension_scores_has_exit_reason_column(tmp_path: Path):
    db_path = tmp_path / "fresh.db"
    conn = sqlite3.connect(db_path)
    try:
        apply_evaluation_schema(conn)
        cols = [row[1] for row in conn.execute("PRAGMA table_info(dimension_scores)").fetchall()]
        assert "exit_reason" in cols
        # Verify it is nullable by inserting a row without that column.
        conn.execute(
            "INSERT INTO dimension_scores (dimension, coverage_pct) VALUES (?, ?)",
            ("security", 50.0),
        )
        row = conn.execute(
            "SELECT exit_reason FROM dimension_scores WHERE dimension = ?",
            ("security",),
        ).fetchone()
        assert row[0] is None
    finally:
        conn.close()


def test_schema_version_bumped_to_6():
    assert SCHEMA_VERSION == 6


def test_upgrade_from_v4_adds_exit_reason(tmp_path: Path):
    """Existing v4 DB gets the new column via _upgrade_v4_to_v5."""
    db_path = tmp_path / "v4.db"
    conn = sqlite3.connect(db_path)
    try:
        # Simulate a v4 DB: write the existing schema without exit_reason.
        conn.executescript("""
            CREATE TABLE dimension_scores (
                dimension       TEXT PRIMARY KEY,
                score           REAL,
                grade           TEXT,
                confidence      TEXT,
                files_read      INTEGER NOT NULL DEFAULT 0,
                source_count    INTEGER NOT NULL DEFAULT 0,
                coverage_pct    REAL NOT NULL DEFAULT 0.0,
                completed_at    TEXT NOT NULL DEFAULT (datetime('now'))
            );
            PRAGMA user_version = 4;
        """)
        apply_evaluation_schema(conn)
        cols = [row[1] for row in conn.execute("PRAGMA table_info(dimension_scores)").fetchall()]
        assert "exit_reason" in cols
        # Applying walks all the way to the current schema version.
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        conn.close()
