"""Index sync primitives: pid liveness, legacy-run classification, status upserts and orphan rows."""
from __future__ import annotations

import os
from pathlib import Path

from quodeq.data.fs.run_status_store import RunState, RunStatus, write_status
from quodeq.data.sqlite.run_index import open_index, sync_index
from quodeq.data.sqlite.index_sync import (
    _is_pid_alive,
    sync_legacy_run,
    upsert_from_status,
)
from tests.data._index_sync_helpers import _make_run_dir


def test_is_pid_alive_current_process() -> None:
    assert _is_pid_alive(os.getpid()) is True


def test_is_pid_alive_dead_pid() -> None:
    assert _is_pid_alive(999999999) is False


def test_legacy_scan_json_present_is_done(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r1")
        (run / "scan.json").write_text("{}")
        sync_legacy_run(db, run, project_uuid="p", run_id="r1")
        row = db.execute("SELECT state, exit_reason FROM runs WHERE job_id = ?", ("ext-r1",)).fetchone()
        assert row == ("done", None)
    finally:
        db.close()


def test_legacy_live_pid_is_running(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r2")
        (run / ".pid").write_text(str(os.getpid()))
        sync_legacy_run(db, run, project_uuid="p", run_id="r2")
        row = db.execute("SELECT state, exit_reason FROM runs WHERE job_id = ?", ("ext-r2",)).fetchone()
        assert row[0] == "running"
        assert row[1] is None
    finally:
        db.close()


def test_legacy_dead_pid_is_cancelled(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r3")
        (run / ".pid").write_text("999999999")
        sync_legacy_run(db, run, project_uuid="p", run_id="r3")
        row = db.execute("SELECT state, exit_reason FROM runs WHERE job_id = ?", ("ext-r3",)).fetchone()
        assert row[0] == "cancelled"
        assert row[1] == "stale_legacy_pid_dead"
    finally:
        db.close()


def test_legacy_no_pid_no_scan_is_cancelled(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r4")
        sync_legacy_run(db, run, project_uuid="p", run_id="r4")
        row = db.execute("SELECT state, exit_reason FROM runs WHERE job_id = ?", ("ext-r4",)).fetchone()
        assert row[0] == "cancelled"
        assert row[1] == "stale_legacy_no_pid"
    finally:
        db.close()


def test_upsert_from_status_inserts_new_row(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r5")
        write_status(run, RunStatus(state=RunState.PENDING, job_id="ext-r5",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=["security"]))
        upsert_from_status(db, run, project_uuid="p", run_id="r5")
        row = db.execute(
            "SELECT state, project_uuid, run_id FROM runs WHERE job_id = ?",
            ("ext-r5",),
        ).fetchone()
        assert row == ("pending", "p", "r5")
    finally:
        db.close()


def test_upsert_updates_existing_row(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r6")
        write_status(run, RunStatus(state=RunState.RUNNING, job_id="ext-r6",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=[]))
        upsert_from_status(db, run, project_uuid="p", run_id="r6")
        write_status(run, RunStatus(state=RunState.DONE, job_id="ext-r6",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=[]))
        upsert_from_status(db, run, project_uuid="p", run_id="r6")
        row = db.execute("SELECT state FROM runs WHERE job_id = ?", ("ext-r6",)).fetchone()
        assert row[0] == "done"
    finally:
        db.close()


def test_sync_index_deletes_orphan_non_terminal_row(tmp_path: Path) -> None:
    """A non-terminal row whose run_dir is missing on disk must be removed.

    Reproduces the production trap where a row gets stuck as `running` because
    `check_stale_and_promote` reads `.heartbeat` from a run_dir that no longer
    exists, so the heartbeat is unreadable and the row is never promoted.
    """
    reports = tmp_path / "reports"
    reports.mkdir()
    db = open_index(tmp_path / "idx.db")
    try:
        # Row points at a run_dir that does not exist on disk.
        ghost_dir = reports / "ghost-project" / "ghost-run"
        db.execute(
            "INSERT INTO runs (job_id, project_uuid, run_id, run_dir, state, "
            "started_at, updated_at, status_mtime) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ext-ghost", "ghost-project", "ghost-run", str(ghost_dir),
                "running", "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00", 0,
            ),
        )
        db.commit()

        sync_index(db, reports)

        row = db.execute(
            "SELECT job_id FROM runs WHERE job_id = ?", ("ext-ghost",),
        ).fetchone()
        assert row is None, "orphan non-terminal row should be removed by sync_index"
    finally:
        db.close()


def test_sync_index_keeps_orphan_terminal_row(tmp_path: Path) -> None:
    """A terminal-state row whose run_dir is missing should be preserved.

    Users may prune old run dirs to save disk; the index entry is the only
    record of that run's outcome and must not be silently deleted.
    """
    reports = tmp_path / "reports"
    reports.mkdir()
    db = open_index(tmp_path / "idx.db")
    try:
        ghost_dir = reports / "p" / "old-run"
        db.execute(
            "INSERT INTO runs (job_id, project_uuid, run_id, run_dir, state, "
            "started_at, updated_at, status_mtime) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ext-old", "p", "old-run", str(ghost_dir),
                "done", "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00", 0,
            ),
        )
        db.commit()

        sync_index(db, reports)

        row = db.execute(
            "SELECT state FROM runs WHERE job_id = ?", ("ext-old",),
        ).fetchone()
        assert row is not None and row[0] == "done"
    finally:
        db.close()


def test_sync_index_keeps_rows_whose_run_dir_exists(tmp_path: Path) -> None:
    """Sanity check: rows backed by a real run_dir survive the orphan sweep."""
    reports = tmp_path / "reports"
    run = _make_run_dir(reports, "p", "real-run")
    write_status(
        run, RunStatus(
            state=RunState.RUNNING, job_id="ext-real-run",
            started_at="2026-04-20T00:00:00+00:00", dimensions=[], pid=os.getpid(),
        ),
    )
    db = open_index(tmp_path / "idx.db")
    try:
        sync_index(db, reports)
        row = db.execute(
            "SELECT state FROM runs WHERE job_id = ?", ("ext-real-run",),
        ).fetchone()
        assert row is not None and row[0] == "running"
    finally:
        db.close()
