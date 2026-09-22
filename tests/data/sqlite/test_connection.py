import sqlite3
from pathlib import Path

import pytest

from quodeq.data.sqlite._migrations import SchemaVersionError
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


def test_open_evaluation_db_wraps_sqlite_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "quodeq.data.sqlite.connection.apply_evaluation_schema",
        lambda conn: (_ for _ in ()).throw(sqlite3.OperationalError("disk I/O error")),
    )
    with pytest.raises(RuntimeError, match="Could not open evaluation database"):
        with open_evaluation_db(tmp_path / "run1"):
            pass


def _spy_on_connect(monkeypatch):
    """Wrap sqlite3.connect as used by the connection module so the test can
    get its hands on the sqlite3.Connection object even when open_evaluation_db
    never yields it (setup-failure paths)."""
    captured: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def spy(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        captured.append(conn)
        return conn

    monkeypatch.setattr("quodeq.data.sqlite.connection.sqlite3.connect", spy)
    return captured


def test_open_evaluation_db_closes_connection_when_operational_error_wrapped(
    tmp_path, monkeypatch
):
    """Regression test: a setup failure that gets wrapped as RuntimeError
    (sqlite3.OperationalError path) must still close the underlying
    connection instead of leaking it."""
    captured = _spy_on_connect(monkeypatch)
    monkeypatch.setattr(
        "quodeq.data.sqlite.connection.apply_evaluation_schema",
        lambda conn: (_ for _ in ()).throw(sqlite3.OperationalError("disk I/O error")),
    )
    with pytest.raises(RuntimeError, match="Could not open evaluation database"):
        with open_evaluation_db(tmp_path / "run1"):
            pass

    assert len(captured) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        captured[0].execute("SELECT 1")


def test_open_evaluation_db_closes_connection_when_schema_version_error_reraised(
    tmp_path, monkeypatch
):
    """Regression test: SchemaVersionError (a sqlite3.DatabaseError) is
    deliberately re-raised unchanged for callers' graceful-degradation
    fallback, but the connection must still be closed before it propagates."""
    captured = _spy_on_connect(monkeypatch)
    monkeypatch.setattr(
        "quodeq.data.sqlite.connection.apply_evaluation_schema",
        lambda conn: (_ for _ in ()).throw(SchemaVersionError("schema version 99 unsupported")),
    )
    with pytest.raises(SchemaVersionError):
        with open_evaluation_db(tmp_path / "run2"):
            pass

    assert len(captured) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        captured[0].execute("SELECT 1")
