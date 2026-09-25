"""Bounded reads through EvaluationsIndex.

- A *states* filter on ``list()`` must narrow the SQL query, not force
  a fetch-all that gets filtered in Python.
- ``get_status`` on an already-indexed "ext-" id must resolve the run
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


def test_internal_jobs_logs_and_returns_empty_when_list_jobs_raises(
    tmp_path: Path, monkeypatch,
) -> None:
    from unittest.mock import patch

    reports_root = tmp_path / "reports"
    index = _make_index(tmp_path, reports_root)

    def _raise(*_args, **_kwargs):
        raise AttributeError("no list_jobs on this store")

    monkeypatch.setattr(index._jobs, "list_jobs", _raise)

    with patch("quodeq.services._evaluations_index._logger.warning") as warning:
        result = index._internal_jobs()

    assert result == []
    assert warning.called
    assert "list_jobs failed" in warning.call_args.args[0]


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


def _seed_internal(reports_root: Path, project: str, run_id: str, job_id: str) -> None:
    run_dir = reports_root / project / run_id
    run_dir.mkdir(parents=True)
    write_status(
        run_dir,
        RunStatus(state=RunState.DONE, job_id=job_id,
                  started_at="2026-05-22T19:00:00+00:00", dimensions=["security"]),
    )


def test_get_status_of_an_indexed_internal_run_skips_the_full_sync(
    tmp_path: Path, monkeypatch,
) -> None:
    reports_root = tmp_path / "reports"
    _seed_internal(reports_root, "proj", "run-1", "job-abc")
    _seed_status(reports_root, "proj", "other", RunState.DONE)
    index = _make_index(tmp_path, reports_root)
    index.list(reports_dir=reports_root)

    def no_full_sync(db, root):
        raise AssertionError("full sync for a run the index already knows")

    monkeypatch.setattr(_run_index, "sync_index", no_full_sync)

    snapshot = index.get_status("job-abc", reports_dir=reports_root)

    assert snapshot is not None
    assert snapshot.output_run_id == "run-1"


def test_get_status_of_an_unindexed_internal_run_falls_back_to_the_full_sync(
    tmp_path: Path,
) -> None:
    reports_root = tmp_path / "reports"
    _seed_internal(reports_root, "proj", "run-1", "job-abc")
    index = _make_index(tmp_path, reports_root)

    snapshot = index.get_status("job-abc", reports_dir=reports_root)

    assert snapshot is not None
    assert snapshot.output_run_id == "run-1"


def _spy_tail(monkeypatch) -> list[Path]:
    tailed: list[Path] = []

    def spy(run_dir, max_lines=500):
        tailed.append(run_dir)
        return ["log line"]

    monkeypatch.setattr("quodeq.services._run_status_readers.tail_run_log", spy)
    return tailed


def test_list_tails_the_run_log_only_for_running_rows(tmp_path: Path, monkeypatch) -> None:
    reports_root = tmp_path / "reports"
    for i in range(3):
        _seed_status(reports_root, "p", f"done-{i}", RunState.DONE)
    _seed_status(reports_root, "p", "live-1", RunState.RUNNING)
    index = _make_index(tmp_path, reports_root)
    tailed = _spy_tail(monkeypatch)

    entries = index.list(reports_dir=reports_root)

    by_run = {e.output_run_id: e for e in entries}
    assert [p.name for p in tailed] == ["live-1"]
    assert by_run["live-1"].logs == ["log line"]
    assert by_run["done-0"].logs == []


def test_get_status_still_tails_the_log_of_a_finished_run(tmp_path: Path, monkeypatch) -> None:
    reports_root = tmp_path / "reports"
    _seed_status(reports_root, "p", "done-0", RunState.DONE)
    index = _make_index(tmp_path, reports_root)
    tailed = _spy_tail(monkeypatch)

    snapshot = index.get_status("ext-done-0", reports_dir=reports_root)

    assert snapshot is not None
    assert snapshot.logs == ["log line"]
    assert len(tailed) == 1
