"""Regression: v3 -> v4 migration must invalidate the projection checkpoint.

Reasoning: the v3 schema's CHECK constraint silently dropped every 'major'
severity finding at insert time (INSERT OR IGNORE swallowed the constraint
violation). The v4 schema widens the CHECK, but rows that were never
inserted at v3 won't appear just because the CHECK now accepts them.

Without this invalidation, a long-running install that was already
projected at v3 would carry the data loss forward into v4 — the user
would see the schema fix but not the data fix.

The migration therefore clears the projection checkpoint and projected-log
size so the next ``ensure_projected`` call sees the DB as "never projected"
and triggers a full rebuild. The rebuild path itself (engine.rebuild) calls
``clear_all`` before re-inserting, so the migration doesn't need to truncate
findings directly — leaving existing rows in place keeps the migration
non-destructive for callers that never re-read.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def _create_v3_db_with_critical_only(db_path: Path) -> None:
    """Synthesize a v3 DB: criticals inserted, majors silently dropped, checkpoint set."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        PRAGMA user_version = 3;
        CREATE TABLE findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schema_version INTEGER NOT NULL DEFAULT 1,
            practice_id TEXT NOT NULL, dimension TEXT NOT NULL DEFAULT '',
            requirement TEXT,
            verdict TEXT NOT NULL CHECK (verdict IN ('violation','compliance','dismissed')),
            severity TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','minor')),
            file TEXT NOT NULL DEFAULT '', line INTEGER NOT NULL DEFAULT 0,
            end_line INTEGER NOT NULL DEFAULT 0, title TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '', snippet TEXT NOT NULL DEFAULT '',
            violation_type TEXT NOT NULL DEFAULT '', context TEXT NOT NULL DEFAULT '',
            scope TEXT NOT NULL DEFAULT '', req_refs_json TEXT,
            dedup_key TEXT NOT NULL UNIQUE,
            confidence INTEGER NOT NULL DEFAULT 100,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE run_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE dimension_scores (dimension TEXT PRIMARY KEY, score REAL, grade TEXT, confidence TEXT,
            files_read INTEGER NOT NULL DEFAULT 0, source_count INTEGER NOT NULL DEFAULT 0,
            coverage_pct REAL NOT NULL DEFAULT 0.0, completed_at TEXT NOT NULL DEFAULT (datetime('now')));
        CREATE TABLE principle_grades (
            dimension TEXT NOT NULL, principle_id TEXT NOT NULL,
            score REAL, grade TEXT,
            finding_count INTEGER NOT NULL DEFAULT 0, dismissed_count INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (dimension, principle_id)
        );
    """)
    # Insert one critical (would pass v3 CHECK), and a projection checkpoint
    # to simulate "this DB has been projected once".
    conn.execute(
        "INSERT INTO findings (practice_id, verdict, severity, file, line, reason, dedup_key) "
        "VALUES ('P', 'violation', 'critical', 'a.py', 1, 'r', 'P|a.py|1|violation')"
    )
    conn.execute(
        "INSERT INTO run_meta (key, value) VALUES ('projection_checkpoint', '2026-05-19T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO run_meta (key, value) VALUES ('projection_event_log_size', '12345')"
    )
    conn.commit()
    conn.close()


def test_v3_to_v4_migration_clears_projection_checkpoint(tmp_path: Path) -> None:
    db_path = tmp_path / "evaluation.db"
    _create_v3_db_with_critical_only(db_path)

    from quodeq.data.sqlite.connection import open_evaluation_db

    # First open triggers the migration.
    with open_evaluation_db(tmp_path) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 4, f"Expected v4 after migration, got v{version}"

        # Existing findings stay; the rebuild path clears them when triggered
        # by the next ensure_projected. What matters for this migration is
        # that the projection metadata is cleared so a rebuild *will* run.

        # Checkpoint cleared so ensure_projected treats this as "never projected".
        cp = conn.execute(
            "SELECT value FROM run_meta WHERE key = 'projection_checkpoint'"
        ).fetchone()
        assert cp is None, (
            f"Checkpoint should be cleared after migration so re-projection "
            f"runs, got: {cp!r}"
        )

        size = conn.execute(
            "SELECT value FROM run_meta WHERE key = 'projection_event_log_size'"
        ).fetchone()
        assert size is None, (
            f"Projected-size should be cleared, got: {size!r}"
        )
