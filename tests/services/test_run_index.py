from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from quodeq.services.run_index import (
    RunRow,
    SCHEMA_VERSION,
    UnsupportedIndexSchemaError,
    open_index,
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
        assert v == SCHEMA_VERSION == 1
    finally:
        db.close()


def test_open_is_idempotent_on_existing_v1(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    open_index(db_path).close()
    db = open_index(db_path)
    try:
        v = db.execute("SELECT version FROM schema_version").fetchone()[0]
        assert v == 1
    finally:
        db.close()


def test_open_raises_on_newer_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    raw = sqlite3.connect(db_path)
    raw.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    raw.execute("INSERT INTO schema_version VALUES (99)")
    raw.commit()
    raw.close()
    with pytest.raises(UnsupportedIndexSchemaError):
        open_index(db_path)


def test_open_recovers_from_corrupt_file(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    db_path.write_bytes(b"not a sqlite file")
    db = open_index(db_path)
    try:
        v = db.execute("SELECT version FROM schema_version").fetchone()[0]
        assert v == 1
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
    from quodeq.shared._env import get_index_db_path
    monkeypatch.delenv("QUODEQ_INDEX_DB_PATH", raising=False)
    p = Path(get_index_db_path())
    assert p.name == "index.db"
    assert p.parent.name == ".quodeq"

    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "custom.db"))
    assert Path(get_index_db_path()) == tmp_path / "custom.db"
