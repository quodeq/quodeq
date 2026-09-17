"""Bounded reads through EvaluationsIndex (findings 5390, 5391).

- 5390: a *states* filter on ``list()`` must narrow the SQL query, not force
  a fetch-all that gets filtered in Python.
- 5391: ``get_status`` on an already-indexed "ext-" id must resolve the run
  directly from the index instead of scanning every project dir.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from quodeq.data.fs.run_status_store import RunState, RunStatus, write_status
from quodeq.data.sqlite import run_index as _run_index
from quodeq.services._evaluations_index import EvaluationsIndex
from quodeq.services._job_model import InMemoryJobStore
from quodeq.services.jobs import JobManager


def _seed_status(reports_root: Path, project: str, run_id: str, state: RunState) -> None:
    run_dir = reports_root / project / run_id
    run_dir.mkdir(parents=True)
    write_status(
        run_dir,
        RunStatus(
            state=state,
            job_id=f"ext-{run_id}",
            started_at="2026-05-22T19:00:00+00:00",
            dimensions=["security"],
        ),
    )


def _make_index(tmp_path: Path, reports_root: Path) -> EvaluationsIndex:
    jobs = JobManager(job_store=InMemoryJobStore(), reports_root=reports_root)
    return EvaluationsIndex(
        jobs=jobs, index_db_path=tmp_path / "index.db", reports_root=reports_root,
    )


def test_list_pushes_states_filter_into_sql_instead_of_fetching_every_row(
    tmp_path: Path, monkeypatch,
) -> None:
    reports_root = tmp_path / "reports"
    for i in range(5):
        _seed_status(reports_root, "p", f"done-{i}", RunState.DONE)
    _seed_status(reports_root, "p", "running-1", RunState.RUNNING)
    index = _make_index(tmp_path, reports_root)

    calls: list[dict] = []
    real_list_runs = _run_index.list_runs

    def spy(db, *, limit, states=None):
        calls.append({"limit": limit, "states": states})
        return real_list_runs(db, limit=limit, states=states)

    monkeypatch.setattr(_run_index, "list_runs", spy)

    entries = index.list(limit=1, reports_dir=reports_root, states={"running"})

    assert calls, "list_runs was never called"
    assert calls[0]["states"] == {"running"}
    assert calls[0]["limit"] is not None, "a states filter must not force a fetch-all"
    assert [e.status for e in entries] == ["running"]


def test_get_status_resolves_an_indexed_external_run_without_scanning_projects(
    tmp_path: Path, monkeypatch,
) -> None:
    reports_root = tmp_path / "reports"
    project, run_id = "proj-uuid", "run-uuid"
    _seed_status(reports_root, project, run_id, RunState.DONE)
    index = _make_index(tmp_path, reports_root)

    # Sync once so the index has a row (and a run_dir) for this run.
    index.list(reports_dir=reports_root)

    def explode(self):
        raise AssertionError("must not scan project dirs once the run is indexed")

    monkeypatch.setattr(Path, "iterdir", explode)

    snapshot = index.get_status(f"ext-{run_id}", reports_dir=reports_root)

    assert snapshot is not None
    assert snapshot.output_project == project
    assert snapshot.output_run_id == run_id


def test_get_status_never_syncs_the_cwd_for_an_empty_indexed_run_dir(
    tmp_path: Path, monkeypatch,
) -> None:
    """Finding 5: Path('') is Path('.'), whose is_dir() is True, so a row with
    a blank run_dir made the scoped sync run against the process cwd."""
    reports_root = tmp_path / "reports"
    project, run_id = "proj-uuid", "run-uuid"
    _seed_status(reports_root, project, run_id, RunState.DONE)
    index = _make_index(tmp_path, reports_root)
    index.list(reports_dir=reports_root)

    real_get_run = _run_index.get_run

    def blank_run_dir(db, job_id):
        row = real_get_run(db, job_id)
        return replace(row, run_dir="") if row is not None else None

    synced: list[Path] = []
    real_sync = _run_index.sync_index_for_run

    def spy_sync(db, run_dir):
        synced.append(run_dir)
        real_sync(db, run_dir)

    monkeypatch.setattr(_run_index, "get_run", blank_run_dir)
    monkeypatch.setattr(_run_index, "sync_index_for_run", spy_sync)

    index.get_status(f"ext-{run_id}", reports_dir=reports_root)

    assert synced == [reports_root / project / run_id]


def test_get_status_falls_back_to_a_scan_when_the_run_is_not_yet_indexed(
    tmp_path: Path,
) -> None:
    """No prior sync: get_status must still find a run that only exists on disk."""
    reports_root = tmp_path / "reports"
    project, run_id = "proj-uuid", "run-uuid"
    _seed_status(reports_root, project, run_id, RunState.DONE)
    index = _make_index(tmp_path, reports_root)

    snapshot = index.get_status(f"ext-{run_id}", reports_dir=reports_root)

    assert snapshot is not None
    assert snapshot.output_run_id == run_id
