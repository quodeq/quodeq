"""An index-served job carries the commit it evaluates and its project's git origin."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.data.fs.run_status_store import RunState, RunStatus, write_status
from quodeq.services.filesystem import FilesystemActionProvider
from quodeq.services.wiring import run_index


def _register(tmp_path: Path, run_id: str, *, commit: str | None, origin: str | None) -> FilesystemActionProvider:
    reports = tmp_path / "reports"
    run = reports / "proj-x" / run_id
    run.mkdir(parents=True)
    if origin is not None:
        (run.parent / "repository_info.json").write_text(json.dumps({"uuid": "proj-x", "originUrl": origin}))
    write_status(run, RunStatus(
        state=RunState.RUNNING, job_id=f"ext-{run_id}",
        started_at="2026-10-08T06:00:00+00:00", dimensions=["security"], commit_sha=commit,
    ))
    db = run_index.open_index(tmp_path / "idx.db")
    try:
        run_index.sync_index_for_run(db, run)
    finally:
        db.close()
    return FilesystemActionProvider(index_db_path=tmp_path / "idx.db", reports_root=reports)


def test_snapshot_reads_commit_and_origin(tmp_path: Path) -> None:
    provider = _register(tmp_path, "r1", commit="7e506ae1234", origin="https://github.com/quodeq/quodeq")
    snap = provider.get_evaluation_status("ext-r1", reports_dir=str(tmp_path / "reports"))
    assert snap.commit_sha == "7e506ae1234"
    assert snap.origin_url == "https://github.com/quodeq/quodeq"


def test_snapshot_without_commit_or_origin(tmp_path: Path) -> None:
    provider = _register(tmp_path, "r2", commit=None, origin=None)
    snap = provider.get_evaluation_status("ext-r2", reports_dir=str(tmp_path / "reports"))
    assert snap.commit_sha is None
    assert snap.origin_url is None
