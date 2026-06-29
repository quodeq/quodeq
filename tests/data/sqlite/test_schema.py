"""Sanity checks on schema DDL strings."""
from __future__ import annotations

from pathlib import Path

from quodeq.data.sqlite import _schema
from quodeq.data.sqlite._schema import SCHEMA_VERSION
from quodeq.data.sqlite.connection import open_evaluation_db


def test_evaluation_ddl_creates_findings_table():
    assert "CREATE TABLE findings" in _schema.EVALUATION_DDL
    assert "CHECK (verdict IN ('violation','compliance','dismissed'))" in _schema.EVALUATION_DDL


def test_evaluation_ddl_includes_fts5():
    assert "USING fts5" in _schema.EVALUATION_DDL
    assert "content='findings'" in _schema.EVALUATION_DDL


def test_evaluation_ddl_sets_user_version_to_schema_version():
    assert f"PRAGMA user_version = {_schema.SCHEMA_VERSION}" in _schema.EVALUATION_DDL


def test_evaluation_ddl_includes_confidence_column():
    assert "confidence" in _schema.EVALUATION_DDL


def test_evaluation_ddl_includes_provenance_downgrade_column():
    assert "provenance_downgrade" in _schema.EVALUATION_DDL


def test_schema_version_is_6() -> None:
    assert SCHEMA_VERSION == 6


def test_principle_grades_table_exists(tmp_path: Path) -> None:
    with open_evaluation_db(tmp_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='principle_grades'"
        ).fetchone()
        assert row is not None


def test_principle_grades_columns(tmp_path: Path) -> None:
    with open_evaluation_db(tmp_path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(principle_grades)")}
    assert cols == {
        "dimension", "principle_id", "score", "grade",
        "finding_count", "dismissed_count", "completed_at",
    }


def test_principle_grades_primary_key_is_dimension_principle(tmp_path: Path) -> None:
    with open_evaluation_db(tmp_path) as conn:
        # Insert two rows that share dimension but differ on principle -- both should fit.
        conn.execute(
            "INSERT INTO principle_grades (dimension, principle_id, score, grade) "
            "VALUES (?, ?, ?, ?)", ("Security", "P1", 7.0, "B"),
        )
        conn.execute(
            "INSERT INTO principle_grades (dimension, principle_id, score, grade) "
            "VALUES (?, ?, ?, ?)", ("Security", "P2", 8.0, "A"),
        )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM principle_grades").fetchone()[0]
        assert count == 2
