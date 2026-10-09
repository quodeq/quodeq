"""Evaluation DB v9 -> v10: unplaced findings move out of ``findings``."""
import sqlite3

import pytest

from quodeq.data.sqlite.connection import apply_evaluation_schema


def _v9_db() -> sqlite3.Connection:
    """A v9 database: today's schema without the v10 table and triggers."""
    conn = sqlite3.connect(":memory:")
    apply_evaluation_schema(conn)
    conn.executescript("""
        DROP TRIGGER findings_require_principle;
        DROP TRIGGER findings_keep_principle;
        DROP TABLE unmapped_findings;
        PRAGMA user_version = 9;
    """)
    return conn


def _insert(conn: sqlite3.Connection, practice_id: str, key: str) -> None:
    conn.execute(
        "INSERT INTO findings (practice_id, requirement, verdict, severity, dedup_key) "
        "VALUES (?, 'ACC-PER-01', 'violation', 'major', ?)", (practice_id, key),
    )


def test_blank_principle_rows_move_to_unmapped_and_placed_rows_stay() -> None:
    conn = _v9_db()
    _insert(conn, "", "blank")
    _insert(conn, "Perceivable", "placed")

    apply_evaluation_schema(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 11
    assert [r[0] for r in conn.execute("SELECT dedup_key FROM findings")] == ["placed"]
    moved = conn.execute("SELECT requirement, unmapped_reason FROM unmapped_findings").fetchall()
    assert moved == [("ACC-PER-01", "missing_principle")]


def test_after_the_upgrade_a_blank_principle_cannot_be_written() -> None:
    conn = _v9_db()
    apply_evaluation_schema(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert(conn, "", "blank")
    _insert(conn, "Perceivable", "placed")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE findings SET practice_id = '' WHERE dedup_key = 'placed'")


def test_an_interrupted_upgrade_re_runs_cleanly() -> None:
    conn = _v9_db()
    _insert(conn, "", "blank")
    apply_evaluation_schema(conn)
    conn.execute("PRAGMA user_version = 9")  # the version bump never landed

    apply_evaluation_schema(conn)

    assert conn.execute("SELECT count(*) FROM unmapped_findings").fetchone()[0] == 1
