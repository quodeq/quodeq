from __future__ import annotations
from quodeq.services.run_index import open_index, list_runs_for_project

def _insert(db, *, job_id, project, run_id, state, started_at):
    db.execute(
        "INSERT INTO runs (job_id, project_uuid, run_id, run_dir, state, "
        "started_at, updated_at, status_mtime) VALUES (?,?,?,?,?,?,?,?)",
        (job_id, project, run_id, f"/x/{run_id}", state, started_at, started_at, 0),
    )

def test_list_runs_for_project_filters_and_orders(tmp_path):
    db = open_index(tmp_path / "index.db")
    with db:
        _insert(db, job_id="ext-a", project="P1", run_id="a", state="done", started_at="2026-01-01T00:00:00Z")
        _insert(db, job_id="ext-b", project="P1", run_id="b", state="done", started_at="2026-03-01T00:00:00Z")
        _insert(db, job_id="ext-c", project="P2", run_id="c", state="done", started_at="2026-02-01T00:00:00Z")
    rows = list_runs_for_project(db, "P1")
    assert [r.run_id for r in rows] == ["b", "a"]
    assert all(r.project_uuid == "P1" for r in rows)

def test_list_runs_for_project_empty(tmp_path):
    db = open_index(tmp_path / "index.db")
    assert list_runs_for_project(db, "nope") == []
