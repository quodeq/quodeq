"""EvaluationsIndex.list() limit pushdown: dedup collisions and state filters must not lose DB rows."""
from __future__ import annotations

from pathlib import Path

from quodeq.core.run.job_status import JobStatus
from quodeq.services._evaluations_index import EvaluationsIndex
from quodeq.services._job_model import Job, InMemoryJobStore
from quodeq.services.jobs import JobManager
from quodeq.data.fs.run_status_store import RunState, RunStatus, write_status


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
            RunStatus(
                state=RunState.DONE,
                job_id=f"ext-{run_id}",
                started_at=started_at,
                dimensions=["security"],
            ),
        )

    store = InMemoryJobStore()
    store.put(
        Job(
            job_id="internal-stale",
            status=JobStatus.RUNNING,
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
            RunStatus(
                state=state,
                job_id=f"ext-{run_id}",
                started_at=started_at,
                dimensions=["security"],
                # Live PID: a running row with a dead pid gets promoted to
                # cancelled(stale_detected) by sync_index and would drop out
                # of the filter for an unrelated reason.
                pid=os.getpid() if state is RunState.RUNNING else None,
            ),
        )

    jobs = JobManager(job_store=InMemoryJobStore(), reports_root=reports_root)
    index = EvaluationsIndex(
        jobs=jobs, index_db_path=tmp_path / "index.db", reports_root=reports_root,
    )

    entries = index.list(limit=2, reports_dir=reports_root, states={"running"})

    assert [e.output_run_id for e in entries] == ["run-running-new", "run-running-mid"], (
        [(e.output_run_id, e.status) for e in entries]
    )
