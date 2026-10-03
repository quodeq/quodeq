"""Run index open/recovery semantics, RunRow and the index DB path setting."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from quodeq.data.sqlite.run_index import (
    RunRow,
    SCHEMA_VERSION,
    open_index,
    read_run_dates,
    write_run_dates,
)


def test_open_creates_schema_on_fresh_path(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    db = open_index(db_path)
    try:
        cols = {row[1] for row in db.execute("PRAGMA table_info(runs)").fetchall()}
        expected = {
            "job_id", "project_uuid", "run_id", "run_dir", "state",
            "phase", "current_dimension", "started_at", "updated_at",
            "finalized_at", "heartbeat_at", "pid", "exit_reason", "status_mtime",
        }
        assert expected <= cols
        idx = {row[1] for row in db.execute("PRAGMA index_list(runs)").fetchall()}
        assert "idx_runs_state" in idx
        assert "idx_runs_started_at" in idx
        v = db.execute("SELECT version FROM schema_version").fetchone()[0]
        assert v == SCHEMA_VERSION == 2
    finally:
        db.close()


def test_open_is_idempotent_on_existing_current(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    open_index(db_path).close()
    db = open_index(db_path)
    try:
        v = db.execute("SELECT version FROM schema_version").fetchone()[0]
        assert v == SCHEMA_VERSION
    finally:
        db.close()


def test_open_preserves_rows_on_current_schema(tmp_path: Path) -> None:
    """Reopening a current-schema index must NOT wipe it.

    Guards the load-bearing counterpart to the downgrade recovery: open_index
    discards-and-rebuilds ONLY when version > SCHEMA_VERSION. If that condition
    ever loosened to fire on the equal-version path, every reopen would destroy
    the user's index — this row survives reopen, so that regression fails loudly.
    """
    db_path = tmp_path / "index.db"
    db = open_index(db_path)
    db.execute(
        "INSERT INTO runs (job_id, project_uuid, run_id, run_dir, state, "
        "started_at, updated_at, status_mtime) "
        "VALUES ('ext-keep', 'p', 'keep', '/p/keep', 'done', '0', '0', 0)"
    )
    db.commit()
    db.close()

    db = open_index(db_path)
    try:
        kept = db.execute("SELECT state FROM runs WHERE job_id = 'ext-keep'").fetchone()
        assert kept is not None and kept[0] == "done"
    finally:
        db.close()


def test_open_recovers_from_newer_schema(tmp_path: Path) -> None:
    """A downgraded index.db (schema newer than this binary) is rebuilt, not fatal.

    Scenario from issue #621: a newer quodeq migrated index.db forward, then the
    user installed an older one. The index is derived state, so open_index
    discards the unusable DB and recreates an empty current-schema one (the next
    sync repopulates it) instead of crashing with a raw schema error.
    """
    db_path = tmp_path / "index.db"
    raw = sqlite3.connect(db_path)
    raw.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    raw.execute("INSERT INTO schema_version VALUES (99)")
    raw.commit()
    raw.close()

    db = open_index(db_path)
    try:
        v = db.execute("SELECT version FROM schema_version").fetchone()[0]
        assert v == SCHEMA_VERSION == 2
        # Full current schema recreated, not just the version table.
        cols = {row[1] for row in db.execute("PRAGMA table_info(runs)").fetchall()}
        assert "job_id" in cols
    finally:
        db.close()


def test_open_recovers_from_corrupt_file(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    db_path.write_bytes(b"not a sqlite file")
    db = open_index(db_path)
    try:
        v = db.execute("SELECT version FROM schema_version").fetchone()[0]
        assert v == SCHEMA_VERSION
    finally:
        db.close()


def test_runrow_dataclass_fields() -> None:
    row = RunRow(
        job_id="ext-x", project_uuid="p", run_id="x", run_dir="/tmp/p/x",
        state="done", phase=None, current_dimension=None,
        started_at="2026-04-20T00:00:00+00:00", updated_at="2026-04-20T00:01:00+00:00",
        finalized_at="2026-04-20T00:01:00+00:00", heartbeat_at=None,
        pid=1234, exit_reason=None, status_mtime=0,
    )
    assert row.job_id == "ext-x"
    assert row.state == "done"


def test_get_index_db_path_default_and_env(tmp_path, monkeypatch) -> None:
    from quodeq.shared.env import get_index_db_path, get_quodeq_dir
    monkeypatch.delenv("QUODEQ_INDEX_DB_PATH", raising=False)
    p = Path(get_index_db_path())
    assert p.name == "index.db"
    # The default follows the state dir (QUODEQ_DIR, else ~/.quodeq), never a fixed home.
    assert p.parent == get_quodeq_dir()

    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "custom.db"))
    assert Path(get_index_db_path()) == tmp_path / "custom.db"


def test_open_migrates_v1_index_in_place(tmp_path: Path) -> None:
    """A v1 index gains the run_dates table and keeps its rows; nothing is wiped."""
    db_path = tmp_path / "index.db"
    raw = sqlite3.connect(db_path)
    raw.executescript(
        "CREATE TABLE runs (job_id TEXT PRIMARY KEY, project_uuid TEXT NOT NULL, "
        "run_id TEXT NOT NULL, run_dir TEXT NOT NULL, state TEXT NOT NULL, phase TEXT, "
        "current_dimension TEXT, started_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
        "finalized_at TEXT, heartbeat_at TEXT, pid INTEGER, exit_reason TEXT, "
        "status_mtime INTEGER NOT NULL);"
        "CREATE TABLE schema_version (version INTEGER NOT NULL);"
        "INSERT INTO schema_version VALUES (1);"
        "INSERT INTO runs VALUES ('p/r1','p','r1','/x','done',NULL,NULL,'2024-01-01T00:00:00Z',"
        "'2024-01-01T00:00:00Z',NULL,NULL,NULL,NULL,0);"
    )
    raw.commit()
    raw.close()

    db = open_index(db_path)
    try:
        assert db.execute("SELECT version FROM schema_version").fetchone()[0] == SCHEMA_VERSION
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
        write_run_dates(db, "p", {"r2": ("2024-02-02", "Feb 2, 2024")})
        assert read_run_dates(db, "p") == {"r2": ("2024-02-02", "Feb 2, 2024")}
    finally:
        db.close()


def test_run_dates_round_trip_is_per_project_and_replaces(tmp_path: Path) -> None:
    db = open_index(tmp_path / "index.db")
    try:
        write_run_dates(db, "a", {"r1": ("2024-01-01", "Jan 1"), "r2": ("2024-01-02", "Jan 2")})
        write_run_dates(db, "b", {"r1": ("2023-01-01", "Jan 1, 2023")})
        write_run_dates(db, "a", {"r1": ("2024-01-09", "Jan 9")})
        write_run_dates(db, "a", {})
        assert read_run_dates(db, "a") == {"r1": ("2024-01-09", "Jan 9"), "r2": ("2024-01-02", "Jan 2")}
        assert read_run_dates(db, "b") == {"r1": ("2023-01-01", "Jan 1, 2023")}
        assert read_run_dates(db, "c") == {}
    finally:
        db.close()
