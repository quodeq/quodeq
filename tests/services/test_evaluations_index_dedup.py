"""Regression test for the EvaluationsIndex list dedup bug.

When the dashboard spawns an evaluation:
- JobManager records the job under a bare UUID job_id
- The subprocess writes status.json with job_id "ext-<run_uuid>"
- The SQLite index syncs that status.json into a row keyed by "ext-<run_uuid>"

These are two different job_id strings for the same on-disk run, so a dedup
keyed on job_id alone leaks the run into the merged list twice -- once with
source="internal" (bare UUID) and once with source="external" (ext- prefix).

The correct dedup key is (output_project, output_run_id). When an internal
job matches an indexed external row, the internal entry wins (in-memory
state is fresher than the file-derived snapshot).
"""
from __future__ import annotations

from pathlib import Path

from quodeq.services._evaluations_index import EvaluationsIndex
from quodeq.services._job_model import Job, InMemoryJobStore
from quodeq.services.jobs import JobManager, STATUS_RUNNING
from quodeq.shared.run_status import RunState, write_status


def _seed_status(reports_root: Path, project: str, run_id: str) -> None:
    """Create a run dir with a status.json matching what a subprocess writes."""
    run_dir = reports_root / project / run_id
    run_dir.mkdir(parents=True)
    write_status(
        run_dir,
        state=RunState.RUNNING,
        job_id=f"ext-{run_id}",
        started_at="2026-05-22T19:00:00+00:00",
        dimensions=["security"],
        phase="analyzing",
        pid=99999,
    )


def test_list_returns_one_entry_for_dashboard_spawned_run(tmp_path: Path) -> None:
    """A dashboard-spawned run must appear exactly once in list(), not twice.

    Reproduces the duplicate-entry bug seen in the dashboard when an internal
    JobManager job and the SQLite-indexed external row both reference the
    same on-disk run.
    """
    reports_root = tmp_path / "reports"
    project = "proj-uuid-1"
    run_id = "run-uuid-1"
    _seed_status(reports_root, project, run_id)

    store = InMemoryJobStore()
    store.put(
        Job(
            job_id="internal-uuid-1",
            status=STATUS_RUNNING,
            command=["python", "-m", "quodeq.cli", "evaluate"],
            started_at="2026-05-22T19:00:00+00:00",
            ended_at=None,
            exit_code=None,
            output_project=project,
            output_run_id=run_id,
        ),
    )
    jobs = JobManager(job_store=store, reports_root=reports_root)

    index = EvaluationsIndex(
        jobs=jobs,
        index_db_path=tmp_path / "index.db",
        reports_root=reports_root,
    )
    entries = index.list(reports_dir=reports_root)

    matching = [
        e for e in entries
        if e.output_project == project and e.output_run_id == run_id
    ]
    assert len(matching) == 1, (
        f"expected exactly one entry for run {project}/{run_id}, "
        f"got {len(matching)}: {[(e.job_id, e.source) for e in matching]}"
    )


def test_external_snapshot_carries_provider_and_model(tmp_path: Path) -> None:
    """An ext- run's status.json provider/model reach the JobSnapshot."""
    reports_root = tmp_path / "reports"
    project = "proj-uuid-pm"
    run_id = "run-uuid-pm"
    run_dir = reports_root / project / run_id
    run_dir.mkdir(parents=True)
    write_status(
        run_dir,
        state=RunState.RUNNING,
        job_id=f"ext-{run_id}",
        started_at="2026-05-22T19:00:00+00:00",
        dimensions=["security"],
        phase="analyzing",
        pid=99999,
        ai_provider="llamacpp",
        ai_model="qwen3.6-27b",
    )

    store = InMemoryJobStore()  # no internal job for this run
    jobs = JobManager(job_store=store, reports_root=reports_root)
    index = EvaluationsIndex(
        jobs=jobs,
        index_db_path=tmp_path / "index.db",
        reports_root=reports_root,
    )
    entries = index.list(reports_dir=reports_root)
    match = [e for e in entries if e.output_run_id == run_id]
    assert len(match) == 1, f"expected one external entry, got {match}"
    snap = match[0]
    assert snap.source == "external"
    assert snap.ai_provider == "llamacpp"
    assert snap.ai_model == "qwen3.6-27b"


def test_external_snapshot_provider_model_absent_when_not_in_status(tmp_path: Path) -> None:
    """When status.json has no provider/model, the snapshot fields are None."""
    reports_root = tmp_path / "reports"
    project = "proj-uuid-pm2"
    run_id = "run-uuid-pm2"
    _seed_status(reports_root, project, run_id)  # no ai_provider/ai_model

    store = InMemoryJobStore()  # no internal job for this run
    jobs = JobManager(job_store=store, reports_root=reports_root)
    index = EvaluationsIndex(
        jobs=jobs,
        index_db_path=tmp_path / "index.db",
        reports_root=reports_root,
    )
    entries = index.list(reports_dir=reports_root)
    match = [e for e in entries if e.output_run_id == run_id]
    assert len(match) == 1, f"expected one external entry, got {match}"
    snap = match[0]
    assert snap.source == "external"
    assert snap.ai_provider is None
    assert snap.ai_model is None


def test_list_prefers_internal_over_indexed_external(tmp_path: Path) -> None:
    """When both an internal and external entry exist for the same run, keep the internal one.

    Rationale: the in-memory JobManager entry reflects live process state
    (command, exit_code, etc.) more accurately than the status.json-derived
    snapshot, which is at best as fresh as the last status.json write.
    """
    reports_root = tmp_path / "reports"
    project = "proj-uuid-2"
    run_id = "run-uuid-2"
    _seed_status(reports_root, project, run_id)

    store = InMemoryJobStore()
    store.put(
        Job(
            job_id="internal-uuid-2",
            status=STATUS_RUNNING,
            command=["python", "-m", "quodeq.cli", "evaluate"],
            started_at="2026-05-22T19:00:00+00:00",
            ended_at=None,
            exit_code=None,
            output_project=project,
            output_run_id=run_id,
        ),
    )
    jobs = JobManager(job_store=store, reports_root=reports_root)

    index = EvaluationsIndex(
        jobs=jobs,
        index_db_path=tmp_path / "index.db",
        reports_root=reports_root,
    )
    entries = index.list(reports_dir=reports_root)

    matching = [
        e for e in entries
        if e.output_project == project and e.output_run_id == run_id
    ]
    assert len(matching) == 1
    assert matching[0].job_id == "internal-uuid-2", (
        f"expected internal entry to win, got job_id={matching[0].job_id!r} "
        f"(source={matching[0].source!r})"
    )
