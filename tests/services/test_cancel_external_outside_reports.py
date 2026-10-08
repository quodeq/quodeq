"""Stop reaches an external run outside the reports folder (a PR review in $RUNNER_TEMP).

Before: the pid lookup only searched the reports folder, found nothing, and
the stale fallback marked the row cancelled while the CI process kept going.
"""
from __future__ import annotations

import os
import signal
from pathlib import Path

from quodeq.data.fs.run_status_store import RunState, RunStatus, write_status
from quodeq.services.filesystem import FilesystemActionProvider
from quodeq.services.jobs import JobManager, JobProcessSeams, ProcessControl
from quodeq.services.wiring import run_index


def _outside_run(tmp_path: Path, db_path: Path) -> Path:
    run = tmp_path / "runner-temp" / "pr-proj" / "pr-run"
    run.mkdir(parents=True)
    write_status(run, RunStatus(
        state=RunState.RUNNING, job_id="ext-pr-run",
        started_at="2026-10-08T06:00:00+00:00", dimensions=["security"], pid=os.getpid(),
    ))
    (run / ".pid").write_text(str(os.getpid()))
    db = run_index.open_index(db_path)
    try:
        run_index.sync_index_for_run(db, run)
    finally:
        db.close()
    return run


def test_stop_signals_a_run_outside_the_reports_folder(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    db_path = tmp_path / "idx.db"
    _outside_run(tmp_path, db_path)
    sent: list[tuple[int, int]] = []

    def fake_kill_tree(pid: int, sig: int = signal.SIGTERM) -> None:
        sent.append((pid, sig))

    control = ProcessControl(kill_tree=fake_kill_tree, pid_alive=lambda _pid: not sent)
    provider = FilesystemActionProvider(
        job_manager=JobManager(JobProcessSeams(process_control=control)),
        index_db_path=db_path, reports_root=reports,
    )
    assert provider.cancel_evaluation("ext-pr-run", reports_dir=str(reports)) is True
    assert (os.getpid(), signal.SIGTERM) in sent
    # The app neither scores nor copies a CI-owned run into its own folder.
    assert list(reports.iterdir()) == []
