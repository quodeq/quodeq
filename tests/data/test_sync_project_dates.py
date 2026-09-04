import json
from pathlib import Path

from quodeq.data.sqlite.run_index import open_index, sync_project_dates, list_runs_for_project


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
        import quodeq.data.sqlite.run_index as ri
        real = ri._upsert_from_status
        def counting(*a, **k):
            calls["n"] += 1
            return real(*a, **k)
        monkeypatch.setattr(ri, "_upsert_from_status", counting)
        sync_project_dates(db, proj, "proj")
        assert calls["n"] == 0, "unchanged runs must not be re-read/upserted"
    finally:
        db.close()


def test_sync_project_dates_batches_the_mtime_lookup(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))
    proj = tmp_path / "evaluations" / "proj"
    for i in range(5):
        _write_status(proj / f"run-{i}", "2026-05-25T22:19:50+00:00")

    db = open_index(tmp_path / "idx.db")
    try:
        sync_project_dates(db, proj, "proj")  # first call: populate all 5 rows

        # sqlite3.Connection is a C type with no instance/class __dict__, so
        # `db.execute` can't be monkeypatched directly (setattr raises
        # AttributeError: object attribute is read-only). Use sqlite3's own
        # SQL tracing hook to observe every statement actually executed.
        executed = []
        db.set_trace_callback(executed.append)

        sync_project_dates(db, proj, "proj")  # second call: nothing changed on disk

        mtime_selects = [s for s in executed if "status_mtime" in s and s.strip().upper().startswith("SELECT")]
        assert len(mtime_selects) == 1, (
            f"expected exactly one batched SELECT for 5 runs, got {len(mtime_selects)}: {mtime_selects}"
        )
    finally:
        db.close()
