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
