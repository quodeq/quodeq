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


from quodeq.shared.run_status import RunState, write_status
from quodeq.services.run_index import (
    get_run, list_runs, rebuild_index, sync_index, sync_index_for_run,
)


def _seed_plan_a_run(root: Path, project: str, run_id: str, state: RunState) -> Path:
    d = root / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    write_status(d, state=state, job_id=f"ext-{run_id}",
                 started_at="2026-04-20T00:00:00+00:00", dimensions=[])
    return d


def test_sync_index_seeds_rows_for_all_runs(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _seed_plan_a_run(reports, "proj1", "runA", RunState.DONE)
    _seed_plan_a_run(reports, "proj1", "runB", RunState.RUNNING)
    legacy = reports / "proj2" / "runC"
    (legacy / "evidence").mkdir(parents=True)
    (legacy / "evidence" / "manifest.json").write_text("{}")
    (legacy / "scan.json").write_text("{}")

    db = open_index(tmp_path / "idx.db")
    try:
        sync_index(db, reports)
        rows = db.execute("SELECT job_id, state FROM runs ORDER BY job_id").fetchall()
        job_ids = {r[0] for r in rows}
        assert job_ids == {"ext-runA", "ext-runB", "ext-runC"}
        # runA and runC should be done.
        states_by_id = dict(rows)
        assert states_by_id["ext-runA"] == "done"
        assert states_by_id["ext-runC"] == "done"
    finally:
        db.close()


def test_sync_index_skips_unchanged_rows(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _seed_plan_a_run(reports, "proj1", "runA", RunState.DONE)
    db = open_index(tmp_path / "idx.db")
    try:
        sync_index(db, reports)
        # Second sync with no filesystem changes should be a no-op for writes to the runs table.
        sync_index(db, reports)
        row_count = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        assert row_count == 1
    finally:
        db.close()


def test_list_runs_ordered_by_started_at_desc(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    older = reports / "p" / "older"
    newer = reports / "p" / "newer"
    (older / "evidence").mkdir(parents=True)
    (newer / "evidence").mkdir(parents=True)
    (older / "evidence" / "manifest.json").write_text("{}")
    (newer / "evidence" / "manifest.json").write_text("{}")
    write_status(older, state=RunState.DONE, job_id="ext-older",
                 started_at="2026-04-19T00:00:00+00:00", dimensions=[])
    write_status(newer, state=RunState.DONE, job_id="ext-newer",
                 started_at="2026-04-20T00:00:00+00:00", dimensions=[])

    db = open_index(tmp_path / "idx.db")
    try:
        sync_index(db, reports)
        rows = list_runs(db)
        assert [r.job_id for r in rows] == ["ext-newer", "ext-older"]
    finally:
        db.close()


def test_list_runs_respects_limit(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    for i in range(5):
        _seed_plan_a_run(reports, "p", f"r{i}", RunState.DONE)
    db = open_index(tmp_path / "idx.db")
    try:
        sync_index(db, reports)
        rows = list_runs(db, limit=3)
        assert len(rows) == 3
    finally:
        db.close()


def test_get_run_returns_row_or_none(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _seed_plan_a_run(reports, "p", "r", RunState.DONE)
    db = open_index(tmp_path / "idx.db")
    try:
        sync_index(db, reports)
        row = get_run(db, "ext-r")
        assert row is not None
        assert row.job_id == "ext-r"
        assert row.state == "done"
        assert get_run(db, "ext-does-not-exist") is None
    finally:
        db.close()


def test_sync_index_for_run_is_scoped(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    a = _seed_plan_a_run(reports, "p", "rA", RunState.RUNNING)
    _seed_plan_a_run(reports, "p", "rB", RunState.RUNNING)
    db = open_index(tmp_path / "idx.db")
    try:
        sync_index_for_run(db, a)
        rows = db.execute("SELECT job_id FROM runs").fetchall()
        assert [r[0] for r in rows] == ["ext-rA"]
    finally:
        db.close()


def test_rebuild_index_empties_and_repopulates(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _seed_plan_a_run(reports, "p", "rA", RunState.DONE)
    _seed_plan_a_run(reports, "p", "rB", RunState.DONE)
    db = open_index(tmp_path / "idx.db")
    try:
        sync_index(db, reports)
        db.execute(
            "INSERT INTO runs (job_id, project_uuid, run_id, run_dir, state, "
            "started_at, updated_at, status_mtime) "
            "VALUES ('phantom', 'p', 'p', '/nope', 'running', '0', '0', 0)"
        )
        db.commit()
        count, elapsed_ms = rebuild_index(db, reports)
        assert count == 2
        assert elapsed_ms >= 0
        rows = {r[0] for r in db.execute("SELECT job_id FROM runs").fetchall()}
        assert rows == {"ext-rA", "ext-rB"}
    finally:
        db.close()
