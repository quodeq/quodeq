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
from quodeq.data.fs.run_status_store import RunState, write_status


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


def test_lost_internal_job_yields_to_the_live_indexed_row(tmp_path: Path) -> None:
    """After a server restart the internal job flips to 'lost' while the
    subprocess keeps running and writing status.json. The truthful ext- row
    must win the merge: before this fix the internal placeholder covered it,
    the live scan disappeared from /api/evaluations, and cancel 409ed.
    """
    import os

    reports_root = tmp_path / "reports"
    project = "proj-uuid-2"
    run_id = "run-uuid-2"
    # Live PID: the surviving subprocess. A dead PID gets promoted to
    # cancelled(stale_detected) by sync_index — correct, but not the
    # scenario under test.
    run_dir = reports_root / project / run_id
    run_dir.mkdir(parents=True)
    write_status(
        run_dir,
        state=RunState.RUNNING,
        job_id=f"ext-{run_id}",
        started_at="2026-05-22T19:00:00+00:00",
        dimensions=["security"],
        phase="analyzing",
        pid=os.getpid(),
    )

    store = InMemoryJobStore()
    store.put(
        Job(
            job_id="internal-uuid-2",
            status="lost",
            command=["python", "-m", "quodeq.cli", "evaluate"],
            started_at="2026-05-22T19:00:00+00:00",
            ended_at="2026-05-22T19:05:00+00:00",
            exit_code=None,
            output_project=project,
            output_run_id=run_id,
        ),
    )
    jobs = JobManager(job_store=store, reports_root=reports_root)
    index = EvaluationsIndex(
        jobs=jobs, index_db_path=tmp_path / "index.db", reports_root=reports_root,
    )

    entries = index.list(reports_dir=reports_root)
    matching = [
        e for e in entries
        if e.output_project == project and e.output_run_id == run_id
    ]
    assert len(matching) == 1, [(e.job_id, e.status) for e in matching]
    assert matching[0].job_id == f"ext-{run_id}"
    assert matching[0].status == "running"


def test_lost_internal_job_without_indexed_row_stays_visible(tmp_path: Path) -> None:
    """A lost job whose run never produced a status.json has no truthful
    replacement — keep the 'lost' placeholder so the user sees what happened."""
    reports_root = tmp_path / "reports"
    reports_root.mkdir(parents=True)

    store = InMemoryJobStore()
    store.put(
        Job(
            job_id="internal-uuid-3",
            status="lost",
            command=["python"],
            started_at="2026-05-22T19:00:00+00:00",
            ended_at="2026-05-22T19:05:00+00:00",
            exit_code=None,
            output_project="proj-x",
            output_run_id="run-x",
        ),
    )
    jobs = JobManager(job_store=store, reports_root=reports_root)
    index = EvaluationsIndex(
        jobs=jobs, index_db_path=tmp_path / "index.db", reports_root=reports_root,
    )

    entries = index.list(reports_dir=reports_root)
    assert [e.status for e in entries] == ["lost"]


def test_list_limit_pushdown_keeps_db_row_that_outranks_a_deduped_job(tmp_path: Path) -> None:
    """Regression for the limit-pushdown fix in ``EvaluationsIndex.list()``.

    A naive ``_run_index.list_runs(db, limit=N)`` (dropping the old
    fetch-all-then-limit behavior without compensating for dedup) can drop
    a DB row that outranks an in-memory job, whenever that job dedupes
    against (and replaces) a *different*, higher-ranked DB row that would
    otherwise have consumed one of the N fetched slots.

    Here three finished runs are index-only (no JobManager entry), oldest
    to newest: run-old (08:00) < run-mid (09:00) < run-newest (10:00). An
    in-memory job shares its (project, run_id) with run-newest -- the
    in-memory record always wins that merge regardless of its own
    timestamp -- but the job's own started_at (00:00) is older than every
    index row. With ``limit=2``:

    - The correct top-2 (fetch-all-then-merge-then-limit) is
      [run-mid (09:00), run-old (08:00)] -- both outrank the stale job.
    - A naive ``limit=2`` DB fetch only pulls [run-newest, run-mid]. Once
      run-newest is dropped by the dedup, run-old was never fetched and
      silently disappears, letting the stale job (00:00) fill the second
      slot instead.

    The fix over-fetches by ``len(internal_jobs)`` so a dedup collision
    never costs a DB row that should have made the cut.
    """
    reports_root = tmp_path / "reports"
    project = "proj-limit"

    for run_id, started_at in (
        ("run-old", "2026-01-01T08:00:00+00:00"),
        ("run-mid", "2026-01-01T09:00:00+00:00"),
        ("run-newest", "2026-01-01T10:00:00+00:00"),
    ):
        run_dir = reports_root / project / run_id
        run_dir.mkdir(parents=True)
        write_status(
            run_dir,
            state=RunState.DONE,
            job_id=f"ext-{run_id}",
            started_at=started_at,
            dimensions=["security"],
        )

    store = InMemoryJobStore()
    store.put(
        Job(
            job_id="internal-stale",
            status=STATUS_RUNNING,
            command=["python", "-m", "quodeq.cli", "evaluate"],
            started_at="2026-01-01T00:00:00+00:00",
            ended_at=None,
            exit_code=None,
            output_project=project,
            output_run_id="run-newest",
        ),
    )
    jobs = JobManager(job_store=store, reports_root=reports_root)

    index = EvaluationsIndex(
        jobs=jobs,
        index_db_path=tmp_path / "index.db",
        reports_root=reports_root,
    )
    entries = index.list(limit=2, reports_dir=reports_root)

    assert [e.output_run_id for e in entries] == ["run-mid", "run-old"], (
        [(e.output_run_id, e.started_at) for e in entries]
    )


def test_list_state_filter_reaches_past_the_limit_window(tmp_path: Path) -> None:
    """``limit`` caps the result, it must not cap how far back a state filter looks.

    The ``states`` filter runs after the merge, on rows the SQL LIMIT already
    truncated. Seeded here: three finished runs (10:00-12:00) newer than three
    running ones (07:00-09:00). ``list(limit=2, states={"running"})`` pushing
    ``LIMIT 2`` down fetches only the two newest — both finished — and the
    filter then returns nothing, even though three matches exist just past the
    window. Reachable via ``GET /api/evaluations?state=running`` and
    ``local_provider_busy``. A filter therefore disables the pushdown.
    """
    import os

    reports_root = tmp_path / "reports"
    project = "proj-states"

    for run_id, started_at, state in (
        ("run-running-old", "2026-01-01T07:00:00+00:00", RunState.RUNNING),
        ("run-running-mid", "2026-01-01T08:00:00+00:00", RunState.RUNNING),
        ("run-running-new", "2026-01-01T09:00:00+00:00", RunState.RUNNING),
        ("run-done-a", "2026-01-01T10:00:00+00:00", RunState.DONE),
        ("run-done-b", "2026-01-01T11:00:00+00:00", RunState.DONE),
        ("run-done-c", "2026-01-01T12:00:00+00:00", RunState.DONE),
    ):
        run_dir = reports_root / project / run_id
        run_dir.mkdir(parents=True)
        write_status(
            run_dir,
            state=state,
            job_id=f"ext-{run_id}",
            started_at=started_at,
            dimensions=["security"],
            # Live PID: a running row with a dead pid gets promoted to
            # cancelled(stale_detected) by sync_index and would drop out of
            # the filter for an unrelated reason.
            pid=os.getpid() if state is RunState.RUNNING else None,
        )

    jobs = JobManager(job_store=InMemoryJobStore(), reports_root=reports_root)
    index = EvaluationsIndex(
        jobs=jobs, index_db_path=tmp_path / "index.db", reports_root=reports_root,
    )

    entries = index.list(limit=2, reports_dir=reports_root, states={"running"})

    assert [e.output_run_id for e in entries] == ["run-running-new", "run-running-mid"], (
        [(e.output_run_id, e.status) for e in entries]
    )
