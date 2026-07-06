import json
from pathlib import Path

from quodeq.services.run_index import open_index, sync_project_dates, list_runs_for_project


def _write_status(run_dir: Path, started_at: str):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "status.json").write_text(json.dumps({
        "schema_version": 1, "job_id": f"job-{run_dir.name}", "state": "done",
        "started_at": started_at, "updated_at": started_at, "finalized_at": started_at,
        "phase": None, "current_dimension": None, "dimensions": [], "pid": None,
        "exit_reason": None, "deadline_at": None,
    }), encoding="utf-8")


def test_syncs_started_at_and_is_mtime_gated(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))
    proj = tmp_path / "evaluations" / "proj"
    _write_status(proj / "run-a", "2026-05-25T22:19:50+00:00")
    _write_status(proj / "run-b", "2026-05-26T09:00:00+00:00")

    db = open_index(tmp_path / "idx.db")
    try:
        sync_project_dates(db, proj, "proj")
        rows = {r.run_id: r.started_at for r in list_runs_for_project(db, "proj")}
        assert rows == {
            "run-a": "2026-05-25T22:19:50+00:00",
            "run-b": "2026-05-26T09:00:00+00:00",
        }
        # Second call, nothing changed on disk -> no upserts (mtime gate).
        calls = {"n": 0}
        import quodeq.services.run_index as ri
        real = ri._upsert_from_status
        def counting(*a, **k):
            calls["n"] += 1
            return real(*a, **k)
        monkeypatch.setattr(ri, "_upsert_from_status", counting)
        sync_project_dates(db, proj, "proj")
        assert calls["n"] == 0, "unchanged runs must not be re-read/upserted"
    finally:
        db.close()
