from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.shared.run_status import RunState, write_status


def _seed_run(reports: Path, project: str, run_id: str, state: RunState) -> Path:
    d = reports / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    write_status(d, state=state, job_id=f"ext-{run_id}",
                 started_at="2026-04-20T00:00:00+00:00", dimensions=[])
    return d


def test_provider_list_evaluations_returns_indexed_rows(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    _seed_run(reports, "p", "rA", RunState.DONE)
    _seed_run(reports, "p", "rB", RunState.DONE)

    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))

    from quodeq.services.filesystem import FilesystemActionProvider
    provider = FilesystemActionProvider(index_db_path=tmp_path / "idx.db")
    jobs = provider.list_evaluations(limit=0, reports_dir=reports)
    job_ids = {j.job_id for j in jobs}
    assert {"ext-rA", "ext-rB"} <= job_ids
    assert all(j.status == "done" for j in jobs if j.job_id.startswith("ext-"))


def test_provider_get_evaluation_status_returns_row(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    _seed_run(reports, "p", "rX", RunState.RUNNING)
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))

    from quodeq.services.filesystem import FilesystemActionProvider
    provider = FilesystemActionProvider(index_db_path=tmp_path / "idx.db")
    snapshot = provider.get_evaluation_status("ext-rX", reports_dir=reports)
    assert snapshot is not None
    assert snapshot.job_id == "ext-rX"
    assert snapshot.status == "running"


def test_get_evaluation_status_promotes_stale_ext_run(tmp_path, monkeypatch) -> None:
    """An ext- run with stale heartbeat + dead PID must be promoted to cancelled
    when the single-run endpoint is hit. Verifies index path is used (not JobManager's
    old filesystem heuristic)."""
    import os
    import time
    from quodeq.shared.run_status import RunState, read_status, write_status

    reports = tmp_path / "reports"
    run = reports / "p" / "stale-run"
    (run / "evidence").mkdir(parents=True)
    (run / "evidence" / "manifest.json").write_text("{}")
    # status.json says running but PID is dead
    write_status(run, state=RunState.RUNNING, job_id="ext-stale-run",
                 started_at="2026-04-20T00:00:00+00:00", dimensions=[], pid=999999999)
    # Heartbeat is 60s old
    heartbeat = run / ".heartbeat"
    heartbeat.touch()
    old = time.time() - 60
    os.utime(heartbeat, (old, old))

    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))

    from quodeq.services.filesystem import FilesystemActionProvider
    provider = FilesystemActionProvider(index_db_path=tmp_path / "idx.db")
    snapshot = provider.get_evaluation_status("ext-stale-run", reports_dir=reports)
    assert snapshot is not None
    assert snapshot.status == "cancelled", f"expected cancelled after stale promotion, got {snapshot.status}"
    # Disk status.json should also be updated.
    disk = read_status(run)
    assert disk["state"] == "cancelled"


def test_provider_list_repeated_call_works(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    _seed_run(reports, "p", "rA", RunState.DONE)
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))

    from quodeq.services.filesystem import FilesystemActionProvider
    provider = FilesystemActionProvider(index_db_path=tmp_path / "idx.db")
    provider.list_evaluations(limit=0, reports_dir=reports)
    jobs = provider.list_evaluations(limit=0, reports_dir=reports)
    assert len(jobs) >= 1
    assert any(j.job_id == "ext-rA" for j in jobs)


def test_list_evaluations_internal_job_overrides_index_row(tmp_path, monkeypatch) -> None:
    """When JobManager has an in-memory job with the same job_id as an index
    row, the in-memory version wins. Covers the Plan B1 precedence rule that
    had no explicit test before.

    Scenario: a dashboard-spawned job is running live (fresh `status="running"`,
    live logs in JobManager). Separately, the SQLite index has a stale row for
    the same job_id (e.g., from an earlier sync that picked up the run_dir).
    The authoritative live state must come from JobManager, not the index.
    """
    from unittest.mock import MagicMock
    from quodeq.shared.run_status import RunState, write_status
    from quodeq.services.filesystem import FilesystemActionProvider
    from quodeq.core.types.job import JobSnapshot

    reports = tmp_path / "reports"
    # Seed an index row for job-id "internal-42" — as if the index already
    # knew about this run from a prior sync.
    run = reports / "p" / "internal-42"
    (run / "evidence").mkdir(parents=True)
    (run / "evidence" / "manifest.json").write_text("{}")
    write_status(
        run, state=RunState.RUNNING, job_id="internal-42",
        started_at="2026-04-20T00:00:00+00:00", dimensions=[],
    )

    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))

    # Stub JobManager.list_jobs to return the authoritative in-memory snapshot
    # with RICHER data (phase="analyzing", current_dimension="security") — the
    # index-synced row wouldn't have those because sync_index reads status.json
    # which is stale.
    live_snapshot = JobSnapshot(
        job_id="internal-42",
        status="running",
        started_at="2026-04-20T00:00:00+00:00",
        phase="analyzing",
        current_dimension="security",
        source="internal",
    )
    fake_jobs = MagicMock()
    fake_jobs.list_jobs.return_value = [live_snapshot]

    provider = FilesystemActionProvider(
        job_manager=fake_jobs,
        index_db_path=tmp_path / "idx.db",
    )
    jobs = provider.list_evaluations(limit=0, reports_dir=reports)

    by_id = {j.job_id: j for j in jobs}
    result = by_id.get("internal-42")
    assert result is not None, f"internal-42 missing from merged list: {by_id.keys()}"
    # The in-memory snapshot won — phase/current_dimension carry through.
    assert result.phase == "analyzing"
    assert result.current_dimension == "security"
    assert result.source == "internal"
    # And JobManager.list_jobs was called with reports_root=None (new contract
    # after the deprecation warning).
    fake_jobs.list_jobs.assert_called_once()
    assert fake_jobs.list_jobs.call_args.kwargs.get("reports_root") is None
