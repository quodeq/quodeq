"""Run index sync, listing, lookup and rebuild against seeded run directories."""
from __future__ import annotations

from pathlib import Path

from quodeq.data.fs.run_status_store import RunState, RunStatus, write_status
from quodeq.data.sqlite.run_index import (
    get_run, list_runs, open_index, rebuild_index, sync_index, sync_index_for_run,
)


def _seed_plan_a_run(root: Path, project: str, run_id: str, state: RunState) -> Path:
    d = root / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    write_status(d, RunStatus(state=state, job_id=f"ext-{run_id}",
                 started_at="2026-04-20T00:00:00+00:00", dimensions=[]))
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
    write_status(older, RunStatus(state=RunState.DONE, job_id="ext-older",
                 started_at="2026-04-19T00:00:00+00:00", dimensions=[]))
    write_status(newer, RunStatus(state=RunState.DONE, job_id="ext-newer",
                 started_at="2026-04-20T00:00:00+00:00", dimensions=[]))

    db = open_index(tmp_path / "idx.db")
    try:
        sync_index(db, reports)
        rows = list_runs(db, limit=None)
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


def test_sync_index_issues_one_status_mtime_query_not_one_per_run(tmp_path: Path):
    evaluations_root = tmp_path / "evaluations"
    project_dir = evaluations_root / "proj-uuid"
    for i in range(3):
        run_dir = project_dir / f"run-{i}"
        run_dir.mkdir(parents=True)
        (run_dir / "status.json").write_text(
            '{"state": "complete", "dimensions": ["security"]}', encoding="utf-8",
        )

    db = open_index(tmp_path / "index.db")

    class ConnectionWrapper:
        """Wrapper to count specific SQL queries."""
        def __init__(self, wrapped_db):
            self._db = wrapped_db
            self.status_mtime_queries = 0

        def execute(self, sql, *args, **kwargs):
            if "SELECT status_mtime FROM runs WHERE job_id" in sql:
                self.status_mtime_queries += 1
            return self._db.execute(sql, *args, **kwargs)

        def __enter__(self):
            self._db.__enter__()
            return self

        def __exit__(self, *args):
            return self._db.__exit__(*args)

        def close(self):
            return self._db.close()

    wrapped = ConnectionWrapper(db)
    try:
        sync_index(wrapped, evaluations_root)

        assert wrapped.status_mtime_queries <= 1, (
            f"expected at most 1 batched status_mtime SELECT, got {wrapped.status_mtime_queries}"
        )
    finally:
        wrapped.close()
