from pathlib import Path
from quodeq.data.sqlite.index_repository import SqliteRunIndex


def test_record_run_and_list(tmp_path: Path):
    idx = SqliteRunIndex(tmp_path)
    idx.record_started(
        project="proj-a", run_id="20260429T100000",
        branch="main", model="claude-opus-4-7",
        started_at="2026-04-29T10:00:00Z",
        db_path=str(tmp_path / "evaluations" / "proj-a" / "20260429T100000" / "evaluation.db"),
    )
    idx.record_finished(
        project="proj-a", run_id="20260429T100000",
        finished_at="2026-04-29T10:05:00Z", state="completed",
    )
    runs = idx.list_runs(project="proj-a")
    assert len(runs) == 1
    assert runs[0].run_id == "20260429T100000"
    assert runs[0].state == "completed"
    assert runs[0].started_at == "2026-04-29T10:00:00Z"
    assert runs[0].finished_at == "2026-04-29T10:05:00Z"


def test_list_runs_sorts_newest_first(tmp_path: Path):
    idx = SqliteRunIndex(tmp_path)
    idx.record_started(project="p", run_id="r1", branch=None, model="m",
                       started_at="2026-04-28T10:00:00Z",
                       db_path="/x/r1/evaluation.db")
    idx.record_started(project="p", run_id="r2", branch=None, model="m",
                       started_at="2026-04-29T10:00:00Z",
                       db_path="/x/r2/evaluation.db")
    runs = idx.list_runs(project="p")
    assert [r.run_id for r in runs] == ["r2", "r1"]


def test_index_does_not_store_scores_or_counts(tmp_path: Path):
    """Mutable state must live in evaluation.db, not the index."""
    import sqlite3
    idx = SqliteRunIndex(tmp_path)
    idx.record_started(project="p", run_id="r1", branch=None, model="m",
                       started_at="2026-04-29T10:00:00Z",
                       db_path="/x/r1/evaluation.db")
    conn = sqlite3.connect(tmp_path / "index.db")
    cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    assert "score" not in cols
    assert "finding_count" not in cols
    assert "total_score" not in cols
