import json
from pathlib import Path

from quodeq.data.fs.report_parser.runs import list_runs
from quodeq.data.fs.report_parser._date_utils import normalize_date


def _make_run(reports: Path, project: str, run_id: str, *, started_at, eval_date=None,
              write_status=True):
    rd = reports / project / run_id
    (rd / "evidence").mkdir(parents=True, exist_ok=True)
    (rd / "evidence" / "manifest.json").write_text(json.dumps({"language_stats": {}}), "utf-8")
    (rd / "evaluation").mkdir(parents=True, exist_ok=True)
    ev = {"schema_version": 1, "dimension": "security", "overallScore": "8.0/10",
          "overallGrade": "Good", "principles": [], "violations": []}
    if eval_date is not None:
        ev["date"] = eval_date
    (rd / "evaluation" / "security.json").write_text(json.dumps(ev), "utf-8")
    if write_status:
        (rd / "status.json").write_text(json.dumps({
            "schema_version": 1, "job_id": f"job-{run_id}", "state": "done",
            "started_at": started_at, "updated_at": started_at, "finalized_at": started_at,
            "phase": None, "current_dimension": None, "dimensions": [], "pid": None,
            "exit_reason": None, "deadline_at": None,
        }), "utf-8")
    return rd


def test_index_date_equals_disk_date(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))
    reports = tmp_path / "evaluations"
    # eval_date == started_at (the real-world invariant): index path must match.
    _make_run(reports, "proj", "run-a", started_at="2026-05-25T22:19:50+00:00",
              eval_date="2026-05-25T22:19:50+00:00")
    runs = list_runs(reports, "proj")
    assert len(runs) == 1
    assert (runs[0].date_iso, runs[0].date_label) == normalize_date("2026-05-25T22:19:50+00:00")


def test_missing_status_falls_back_to_parse_run_date(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))
    reports = tmp_path / "evaluations"
    _make_run(reports, "proj", "run-b", started_at="x", eval_date="2026-06-01T10:00:00+00:00",
              write_status=False)  # not in index -> fallback to evaluation date
    runs = list_runs(reports, "proj")
    assert runs[0].date_iso == normalize_date("2026-06-01T10:00:00+00:00")[0]


def test_dateless_run_gains_started_at_from_index(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))
    reports = tmp_path / "evaluations"
    # No eval date -> disk-only would fall back to run_id; index supplies started_at.
    _make_run(reports, "proj", "run-c", started_at="2026-07-04T05:25:51+00:00", eval_date=None)
    runs = list_runs(reports, "proj")
    assert runs[0].date_iso == normalize_date("2026-07-04T05:25:51+00:00")[0]
