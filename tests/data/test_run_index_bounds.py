"""Bounded-read behavior for the run index.

Split from test_run_index.py (already at 408 lines) rather than growing it.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from quodeq.data.fs.run_status_store import RunState, RunStatus, write_status
from quodeq.data.sqlite import run_index
from quodeq.data.sqlite.run_index import open_index, sync_index


def _seed_plan_a_run(root: Path, project: str, run_id: str, state: RunState) -> Path:
    """Same shape as test_run_index.py's helper -- write a status.json run dir."""
    d = root / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    write_status(d, RunStatus(state=state, job_id=f"ext-{run_id}",
                 started_at="2026-04-20T00:00:00+00:00", dimensions=[]))
    return d


@pytest.fixture
def index_db(tmp_path: Path):
    db = open_index(tmp_path / "idx.db")
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def index_db_with_rows(tmp_path: Path, index_db):
    """An open db synced with two "done" runs and one "running" run."""
    reports = tmp_path / "reports"
    _seed_plan_a_run(reports, "p", "r1", RunState.DONE)
    _seed_plan_a_run(reports, "p", "r2", RunState.DONE)
    _seed_plan_a_run(reports, "p", "r3", RunState.RUNNING)
    sync_index(index_db, reports)
    return index_db


def test_list_runs_has_no_default_limit():
    for fn in (run_index.list_runs, run_index.list_runs_for_project):
        param = inspect.signature(fn).parameters["limit"]
        assert param.default is inspect.Parameter.empty, fn.__name__
        assert param.kind is inspect.Parameter.KEYWORD_ONLY, fn.__name__


def test_list_runs_rejects_a_non_positive_limit(index_db) -> None:
    with pytest.raises(ValueError):
        run_index.list_runs(index_db, limit=0)


def test_list_runs_rejects_a_negative_limit(index_db) -> None:
    with pytest.raises(ValueError):
        run_index.list_runs(index_db, limit=-1)


def test_list_runs_none_limit_returns_every_row(index_db_with_rows) -> None:
    rows = run_index.list_runs(index_db_with_rows, limit=None)
    assert len(rows) == 3


def test_list_runs_filters_states_in_sql(index_db_with_rows) -> None:
    rows = run_index.list_runs(index_db_with_rows, limit=None, states=["running"])
    assert [r.state for r in rows] == ["running"]


def test_list_runs_for_project_none_limit_returns_every_row(index_db_with_rows) -> None:
    rows = run_index.list_runs_for_project(index_db_with_rows, "p", limit=None)
    assert len(rows) == 3


def test_list_runs_for_project_rejects_a_non_positive_limit(index_db) -> None:
    with pytest.raises(ValueError):
        run_index.list_runs_for_project(index_db, "p", limit=0)
