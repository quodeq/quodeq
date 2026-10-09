from __future__ import annotations

import sqlite3
from pathlib import Path

from quodeq.data.sqlite.connection import apply_evaluation_schema

_OLD_TABLE = (
    "CREATE TABLE principle_grades (dimension TEXT, principle_id TEXT, score REAL, grade TEXT, "
    "finding_count INTEGER, dismissed_count INTEGER, completed_at TEXT);"
)


def _columns(conn: sqlite3.Connection) -> list[str]:
    return [r[1] for r in conn.execute("PRAGMA table_info(principle_grades)")]


def _version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def test_v11_adds_confidence_to_principle_grades_and_reaches_the_current_version(tmp_path: Path) -> None:
    fresh = sqlite3.connect(tmp_path / "fresh.db")
    apply_evaluation_schema(fresh)
    assert "confidence" in _columns(fresh)
    with sqlite3.connect(tmp_path / "evaluation.db") as conn:
        conn.executescript(_OLD_TABLE + " PRAGMA user_version = 10;")
        apply_evaluation_schema(conn)
        assert "confidence" in _columns(conn)
        assert _version(conn) == _version(fresh)
    fresh.close()


def test_v10_to_v11_upgrade_is_idempotent_when_the_column_is_already_there(tmp_path: Path) -> None:
    with sqlite3.connect(tmp_path / "evaluation.db") as conn:
        conn.executescript(_OLD_TABLE + " PRAGMA user_version = 10;")
        apply_evaluation_schema(conn)
        conn.execute("PRAGMA user_version = 10")  # re-run the v10 -> v11 step over an upgraded table
        apply_evaluation_schema(conn)  # must not raise "duplicate column"
        assert _columns(conn).count("confidence") == 1
        assert _version(conn) > 10
