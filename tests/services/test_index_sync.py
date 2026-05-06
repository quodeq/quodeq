from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from quodeq.shared.run_status import RunState, write_status
from quodeq.services.run_index import open_index, sync_index
from quodeq.services._index_sync import (
    _is_pid_alive,
    _sync_legacy_run,
    _upsert_from_status,
    _check_stale_and_promote,
)


def test_is_pid_alive_current_process() -> None:
    assert _is_pid_alive(os.getpid()) is True


def test_is_pid_alive_dead_pid() -> None:
    assert _is_pid_alive(999999999) is False


def _make_run_dir(root: Path, project: str, run_id: str) -> Path:
    d = root / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    return d


def test_legacy_scan_json_present_is_done(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r1")
        (run / "scan.json").write_text("{}")
        _sync_legacy_run(db, run, project_uuid="p", run_id="r1")
        row = db.execute("SELECT state, exit_reason FROM runs WHERE job_id = ?", ("ext-r1",)).fetchone()
        assert row == ("done", None)
    finally:
        db.close()


def test_legacy_live_pid_is_running(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r2")
        (run / ".pid").write_text(str(os.getpid()))
        _sync_legacy_run(db, run, project_uuid="p", run_id="r2")
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
        _sync_legacy_run(db, run, project_uuid="p", run_id="r3")
        row = db.execute("SELECT state, exit_reason FROM runs WHERE job_id = ?", ("ext-r3",)).fetchone()
        assert row[0] == "cancelled"
        assert row[1] == "stale_legacy_pid_dead"
    finally:
        db.close()


def test_legacy_no_pid_no_scan_is_cancelled(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r4")
        _sync_legacy_run(db, run, project_uuid="p", run_id="r4")
        row = db.execute("SELECT state, exit_reason FROM runs WHERE job_id = ?", ("ext-r4",)).fetchone()
        assert row[0] == "cancelled"
        assert row[1] == "stale_legacy_no_pid"
    finally:
        db.close()


def test_upsert_from_status_inserts_new_row(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r5")
        write_status(run, state=RunState.PENDING, job_id="ext-r5",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=["security"])
        _upsert_from_status(db, run, project_uuid="p", run_id="r5")
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
        write_status(run, state=RunState.RUNNING, job_id="ext-r6",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=[])
        _upsert_from_status(db, run, project_uuid="p", run_id="r6")
        write_status(run, state=RunState.DONE, job_id="ext-r6",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=[])
        _upsert_from_status(db, run, project_uuid="p", run_id="r6")
        row = db.execute("SELECT state FROM runs WHERE job_id = ?", ("ext-r6",)).fetchone()
        assert row[0] == "done"
    finally:
        db.close()


def test_stale_promotion_old_heartbeat_dead_pid(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r7")
        write_status(run, state=RunState.RUNNING, job_id="ext-r7",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=[], pid=999999999)
        _upsert_from_status(db, run, project_uuid="p", run_id="r7")
        heartbeat = run / ".heartbeat"
        heartbeat.touch()
        old = time.time() - 60
        os.utime(heartbeat, (old, old))

        promoted = _check_stale_and_promote(db, run, project_uuid="p", run_id="r7",
                                            stale_seconds=30)
        assert promoted is True
        row = db.execute("SELECT state, exit_reason FROM runs WHERE job_id = ?", ("ext-r7",)).fetchone()
        assert row[0] == "cancelled"
        assert row[1] == "stale_detected"
        from quodeq.shared.run_status import read_status
        disk = read_status(run)
        assert disk["state"] == "cancelled"
    finally:
        db.close()


def test_stale_promotion_live_pid_not_promoted(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r8")
        write_status(run, state=RunState.RUNNING, job_id="ext-r8",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=[], pid=os.getpid())
        _upsert_from_status(db, run, project_uuid="p", run_id="r8")
        heartbeat = run / ".heartbeat"
        heartbeat.touch()
        old = time.time() - 60
        os.utime(heartbeat, (old, old))

        promoted = _check_stale_and_promote(db, run, project_uuid="p", run_id="r8",
                                            stale_seconds=30)
        assert promoted is False
        row = db.execute("SELECT state FROM runs WHERE job_id = ?", ("ext-r8",)).fetchone()
        assert row[0] == "running"
    finally:
        db.close()


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only: signal.SIGKILL doesn't exist on Windows; use TerminateProcess equivalent in a separate test",
)
def test_stale_promotion_after_sigkill_real_subprocess(tmp_path: Path) -> None:
    """SIGKILL leaves status.json as RUNNING — stale-promote must recover it.

    Spawns a real subprocess so we get a PID that is genuinely alive, records
    it in status.json, then `kill -9`s the process without any cleanup hook
    running. After the heartbeat ages out, `_check_stale_and_promote` must
    mark the run CANCELLED with exit_reason="stale_detected".
    """
    db = open_index(tmp_path / "idx.db")
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        run = _make_run_dir(tmp_path, "p", "r10")
        write_status(
            run,
            state=RunState.RUNNING,
            job_id="ext-r10",
            started_at="2026-04-20T00:00:00+00:00",
            dimensions=[],
            pid=proc.pid,
        )
        _upsert_from_status(db, run, project_uuid="p", run_id="r10")
        heartbeat = run / ".heartbeat"
        heartbeat.touch()

        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=5)
        deadline = time.time() + 2
        while _is_pid_alive(proc.pid) and time.time() < deadline:
            time.sleep(0.05)
        assert not _is_pid_alive(proc.pid), "subprocess PID still alive after kill -9"

        old = time.time() - 120
        os.utime(heartbeat, (old, old))

        promoted = _check_stale_and_promote(
            db, run, project_uuid="p", run_id="r10", stale_seconds=30,
        )
        assert promoted is True
        row = db.execute(
            "SELECT state, exit_reason FROM runs WHERE job_id = ?",
            ("ext-r10",),
        ).fetchone()
        assert row == ("cancelled", "stale_detected")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        db.close()


def test_sync_index_deletes_orphan_non_terminal_row(tmp_path: Path) -> None:
    """A non-terminal row whose run_dir is missing on disk must be removed.

    Reproduces the production trap where a row gets stuck as `running` because
    `_check_stale_and_promote` reads `.heartbeat` from a run_dir that no longer
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
        run, state=RunState.RUNNING, job_id="ext-real-run",
        started_at="2026-04-20T00:00:00+00:00", dimensions=[], pid=os.getpid(),
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


def test_stale_promotion_terminal_state_untouched(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r9")
        write_status(run, state=RunState.DONE, job_id="ext-r9",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=[])
        _upsert_from_status(db, run, project_uuid="p", run_id="r9")
        promoted = _check_stale_and_promote(db, run, project_uuid="p", run_id="r9",
                                            stale_seconds=30)
        assert promoted is False
        row = db.execute("SELECT state FROM runs WHERE job_id = ?", ("ext-r9",)).fetchone()
        assert row[0] == "done"
    finally:
        db.close()
