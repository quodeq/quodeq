from __future__ import annotations

import sqlite3
from pathlib import Path

from quodeq.data.sqlite.connection import apply_evaluation_schema


def test_v11_adds_confidence_to_principle_grades_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "evaluation.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("CREATE TABLE principle_grades (dimension TEXT, principle_id TEXT, score REAL, grade TEXT, finding_count INTEGER, dismissed_count INTEGER, completed_at TEXT); PRAGMA user_version = 10;")
        apply_evaluation_schema(conn)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(principle_grades)")}
        assert "confidence" in cols and conn.execute("PRAGMA user_version").fetchone()[0] == 11
        apply_evaluation_schema(conn)  # second run must not raise "duplicate column"
