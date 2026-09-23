from __future__ import annotations

import pytest

from quodeq.services.runs_unit import _row_to_run_entry
from quodeq.data.sqlite.run_index import RunRow
from quodeq.services import runs_unit as ru
from quodeq.data.sqlite.run_index import open_index


def _row(run_id="r1", state="done", started_at="2026-01-02T03:04:05Z"):
    return RunRow(
        job_id=f"ext-{run_id}", project_uuid="P", run_id=run_id, run_dir=f"/x/{run_id}",
        state=state, phase=None, current_dimension=None, started_at=started_at,
        updated_at=started_at, finalized_at=None, heartbeat_at=None, pid=None,
        exit_reason=None, status_mtime=0,
    )


@pytest.mark.parametrize("state,expected", [
    ("done", "done"), ("complete", "done"), ("finished", "done"),
    ("running", "running"), ("in_progress", "running"), ("pending", "running"), ("finalizing", "running"),
    ("cancelled", "cancelled"), ("canceled", "cancelled"),
    ("failed", "failed"), ("error", "failed"), ("lost", "failed"),
])
def test_row_status_is_the_run_list_status(state, expected):
    row = _row(run_id="r", state=state)
    assert _row_to_run_entry(row)["status"] == expected


def test_unknown_index_state_falls_back_to_done_with_a_warning(caplog):
    row = _row(run_id="r", state="bogus")
    with caplog.at_level("WARNING"):
        assert _row_to_run_entry(row)["status"] == "done"
    assert "bogus" in caplog.text


def test_row_to_run_entry_shape_is_camel_and_score_placeholders():
    entry = _row_to_run_entry(_row(run_id="abc", state="done"))
    assert entry["runId"] == "abc"
    assert entry["status"] == "done"
    assert entry["dateISO"] == "2026-01-02T03:04:05Z"
    assert entry["overallScore"] is None
    assert entry["overallGrade"] is None
    assert entry["dimensionScores"] == {}
    assert not any("_" in k for k in entry)


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
