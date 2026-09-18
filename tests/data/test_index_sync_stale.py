"""Stale-run promotion: dead pids, aged heartbeats, terminal rows and forced cancellation."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from quodeq.data.fs.run_status_store import RunState, RunStatus, write_status
from quodeq.data.sqlite.run_index import open_index
from quodeq.data.sqlite._index_sync import (
    _is_pid_alive,
    _upsert_from_status,
    _check_stale_and_promote,
    force_promote_to_cancelled_stale,
)
from tests._timeouts import budget
from tests.data._index_sync_helpers import _make_run_dir


def test_stale_promotion_old_heartbeat_dead_pid(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r7")
        write_status(run, RunStatus(state=RunState.RUNNING, job_id="ext-r7",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=[], pid=999999999))
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
        from quodeq.data.fs.run_status_store import read_status
        disk = read_status(run)
        assert disk["state"] == "cancelled"
    finally:
        db.close()


def test_stale_promotion_live_pid_not_promoted(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r8")
        write_status(run, RunStatus(state=RunState.RUNNING, job_id="ext-r8",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=[], pid=os.getpid()))
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
            RunStatus(
                state=RunState.RUNNING,
                job_id="ext-r10",
                started_at="2026-04-20T00:00:00+00:00",
                dimensions=[],
                pid=proc.pid,
            ),
        )
        _upsert_from_status(db, run, project_uuid="p", run_id="r10")
        heartbeat = run / ".heartbeat"
        heartbeat.touch()

        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=budget(5))
        deadline = time.time() + budget(2)
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
            proc.wait(timeout=budget(5))
        db.close()


def test_stale_promotion_terminal_state_untouched(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r9")
        write_status(run, RunStatus(state=RunState.DONE, job_id="ext-r9",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=[]))
        _upsert_from_status(db, run, project_uuid="p", run_id="r9")
        promoted = _check_stale_and_promote(db, run, project_uuid="p", run_id="r9",
                                            stale_seconds=30)
        assert promoted is False
        row = db.execute("SELECT state FROM runs WHERE job_id = ?", ("ext-r9",)).fetchone()
        assert row[0] == "done"
    finally:
        db.close()


def test_force_promote_preserves_provider_model_deadline(tmp_path: Path) -> None:
    """force_promote_to_cancelled_stale must carry ai_provider/ai_model/deadline_at
    into the rewritten status.json, consistent with _check_stale_and_promote."""
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r11")
        write_status(
            run,
            RunStatus(
                state=RunState.RUNNING,
                job_id="ext-r11",
                started_at="2026-04-20T00:00:00+00:00",
                dimensions=[],
                pid=999999999,
                ai_provider="llamacpp",
                ai_model="qwen3.6-27b",
                deadline_at="2026-01-01T00:00:00+00:00",
            ),
        )
        _upsert_from_status(db, run, project_uuid="p", run_id="r11")

        promoted = force_promote_to_cancelled_stale(db, "ext-r11", run_dir=run)
        assert promoted is True

        from quodeq.data.fs.run_status_store import read_status
        disk = read_status(run)
        assert disk is not None
        assert disk["state"] == "cancelled"
        assert disk["ai_provider"] == "llamacpp"
        assert disk["ai_model"] == "qwen3.6-27b"
        assert disk["deadline_at"] == "2026-01-01T00:00:00+00:00"
    finally:
        db.close()
