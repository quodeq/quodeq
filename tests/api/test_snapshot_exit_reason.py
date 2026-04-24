"""exit_reason should round-trip from status.json → DB → provider → JobSnapshot."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from quodeq.shared.run_status import RunState, write_status


def _seed_stale_run(reports: Path, project: str, run_id: str) -> Path:
    d = reports / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    # status.json with running state + dead PID; heartbeat 60s old → sync_index
    # will promote to cancelled(stale_detected).
    write_status(d, state=RunState.RUNNING, job_id=f"ext-{run_id}",
                 started_at="2026-04-20T00:00:00+00:00", dimensions=[], pid=999999999)
    heartbeat = d / ".heartbeat"
    heartbeat.touch()
    old = time.time() - 60
    os.utime(heartbeat, (old, old))
    return d


def test_jobsnapshot_has_exit_reason_field() -> None:
    from quodeq.core.types.job import JobSnapshot
    snap = JobSnapshot(
        job_id="ext-x", status="cancelled", exit_reason="stale_detected",
    )
    assert snap.exit_reason == "stale_detected"


def test_jobsnapshot_exit_reason_defaults_to_none() -> None:
    from quodeq.core.types.job import JobSnapshot
    snap = JobSnapshot(job_id="x", status="done")
    assert snap.exit_reason is None


def test_provider_snapshot_surfaces_stale_exit_reason(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    _seed_stale_run(reports, "p", "stale-run")
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))

    from quodeq.services.filesystem import FilesystemActionProvider
    provider = FilesystemActionProvider(index_db_path=tmp_path / "idx.db")
    snap = provider.get_evaluation_status("ext-stale-run", reports_dir=reports)
    assert snap is not None
    assert snap.status == "cancelled"
    assert snap.exit_reason == "stale_detected"


def test_provider_list_surfaces_exit_reason(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    _seed_stale_run(reports, "p", "stale-one")
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))

    from quodeq.services.filesystem import FilesystemActionProvider
    provider = FilesystemActionProvider(index_db_path=tmp_path / "idx.db")
    jobs = provider.list_evaluations(limit=0, reports_dir=reports)
    stale = next((j for j in jobs if j.job_id == "ext-stale-one"), None)
    assert stale is not None
    assert stale.exit_reason == "stale_detected"
