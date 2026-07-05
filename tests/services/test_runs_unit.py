from __future__ import annotations
from quodeq.services._runs_unit import _ui_status, _row_to_run_entry
from quodeq.services.run_index import RunRow

def _row(run_id="r1", state="done", started_at="2026-01-02T03:04:05Z"):
    return RunRow(
        job_id=f"ext-{run_id}", project_uuid="P", run_id=run_id, run_dir=f"/x/{run_id}",
        state=state, phase=None, current_dimension=None, started_at=started_at,
        updated_at=started_at, finalized_at=None, heartbeat_at=None, pid=None,
        exit_reason=None, status_mtime=0,
    )

def test_ui_status_mapping():
    assert _ui_status("done") == "complete"
    assert _ui_status("complete") == "complete"
    assert _ui_status("running") == "in_progress"
    assert _ui_status("in_progress") == "in_progress"
    assert _ui_status("cancelled") == "cancelled"
    assert _ui_status("failed") == "failed"
    assert _ui_status("weird-unknown") == "complete"

def test_row_to_run_entry_shape_is_camel_and_score_placeholders():
    entry = _row_to_run_entry(_row(run_id="abc", state="done"))
    assert entry["runId"] == "abc"
    assert entry["status"] == "complete"
    assert entry["dateISO"] == "2026-01-02T03:04:05Z"
    assert entry["overallScore"] is None
    assert entry["overallGrade"] is None
    assert entry["dimensionScores"] == {}
    assert not any("_" in k for k in entry)


from quodeq.services import _runs_unit as ru

class _Dim:
    def __init__(self, dimension, overall_score, overall_grade):
        self.dimension = dimension
        self.overall_score = overall_score
        self.overall_grade = overall_grade

def test_fill_scores_averages_dimensions(monkeypatch, tmp_path):
    monkeypatch.setattr(ru, "read_run_scalars",
        lambda root, proj, rid: [_Dim("security", "6.0/10", "GOOD"), _Dim("performance", "8.0/10", "GOOD")])
    entry = ru._row_to_run_entry(_row(run_id="r1", state="done"))
    ru._fill_scores(entry, tmp_path, "P", "r1")
    assert entry["dimensionScores"] == {"security": 6.0, "performance": 8.0}
    assert entry["overallScore"] == 7.0
    assert entry["overallGrade"] is not None

def test_fill_scores_skips_in_progress(monkeypatch, tmp_path):
    called = False
    def _boom(*a, **k):
        nonlocal called
        called = True
        return []
    monkeypatch.setattr(ru, "read_run_scalars", _boom)
    entry = ru._row_to_run_entry(_row(run_id="r1", state="running"))
    ru._fill_scores(entry, tmp_path, "P", "r1")
    assert called is False
    assert entry["overallScore"] is None

def test_fill_scores_tolerates_read_error(monkeypatch, tmp_path):
    monkeypatch.setattr(ru, "read_run_scalars", lambda *a, **k: (_ for _ in ()).throw(OSError("gone")))
    entry = ru._row_to_run_entry(_row(run_id="r1", state="done"))
    ru._fill_scores(entry, tmp_path, "P", "r1")
    assert entry["overallScore"] is None


from quodeq.services.run_index import open_index

def test_build_runs_unit_end_to_end(monkeypatch, tmp_path):
    db_path = tmp_path / "index.db"
    db = open_index(db_path)
    with db:
        db.execute(
            "INSERT INTO runs (job_id, project_uuid, run_id, run_dir, state, "
            "started_at, updated_at, status_mtime) VALUES "
            "('ext-a','P','a','/x/a','done','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z',0),"
            "('ext-b','P','b','/x/b','done','2026-02-01T00:00:00Z','2026-02-01T00:00:00Z',0)"
        )
    db.close()
    monkeypatch.setattr(ru, "read_run_scalars", lambda root, proj, rid: [_Dim("security", "5.0/10", "ADEQUATE")])
    rows = ru.build_runs_unit(tmp_path, db_path, "P")
    assert [r["runId"] for r in rows] == ["b", "a"]
    assert rows[0]["overallScore"] == 5.0
    assert rows[0]["dimensionScores"] == {"security": 5.0}
