import sqlite3
from pathlib import Path

from quodeq.data.sqlite.connection import (
    open_evaluation_db,
    EVALUATION_DB_FILENAME,
)


def test_open_evaluation_db_creates_file_in_run_dir(tmp_path: Path):
    with open_evaluation_db(tmp_path) as conn:
        assert isinstance(conn, sqlite3.Connection)
        # WAL is set
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
        # findings table exists
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE name='findings'"
        ).fetchall()
        assert rows == [("findings",)]
    assert (tmp_path / EVALUATION_DB_FILENAME).is_file()


def test_open_evaluation_db_reopen_preserves_data(tmp_path: Path):
    with open_evaluation_db(tmp_path) as conn:
        conn.execute(
            "INSERT INTO findings(practice_id, verdict, severity, dedup_key) "
            "VALUES('p1','violation','medium','k1')",
        )
        conn.commit()
    with open_evaluation_db(tmp_path) as conn:
        n = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        assert n == 1
