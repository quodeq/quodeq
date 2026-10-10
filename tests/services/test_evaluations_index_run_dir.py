"""An external run outside the reports folder (a PR review in $RUNNER_TEMP) is still found."""
from __future__ import annotations

import shutil
from pathlib import Path

from quodeq.data.fs.run_status_store import RunState, RunStatus, write_status
from quodeq.services.filesystem import FilesystemActionProvider
from quodeq.services.wiring import run_index


def _register_outside(tmp_path: Path, run_id: str) -> Path:
    run_dir = tmp_path / "runner-temp" / "proj-x" / run_id
    run_dir.mkdir(parents=True)
    write_status(run_dir, RunStatus(
        state=RunState.RUNNING, job_id=f"ext-{run_id}",
        started_at="2026-10-08T06:00:00+00:00", dimensions=["security"],
    ))
    db = run_index.open_index(tmp_path / "index.db")
    try:
        run_index.sync_index_for_run(db, run_dir)
    finally:
        db.close()
    return run_dir


def _index(tmp_path: Path) -> FilesystemActionProvider:
    reports = tmp_path / "reports"
    reports.mkdir(exist_ok=True)
    return FilesystemActionProvider(index_db_path=tmp_path / "index.db", reports_root=reports)


def test_run_outside_reports_root_is_found_through_the_index(tmp_path: Path) -> None:
    run_dir = _register_outside(tmp_path, "run-1")
    assert _index(tmp_path).get_log_run_dir("ext-run-1") == run_dir


def test_vanished_folder_is_not_returned(tmp_path: Path) -> None:
    run_dir = _register_outside(tmp_path, "run-2")
    shutil.rmtree(run_dir)
    assert _index(tmp_path).get_log_run_dir("ext-run-2") is None
