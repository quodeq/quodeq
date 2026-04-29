"""Verify the CLI lifecycle records run start/finish into the global index."""
from pathlib import Path

from quodeq.data.sqlite.index_repository import SqliteRunIndex


def test_record_run_started_writes_to_global_index(tmp_path: Path, monkeypatch):
    quodeq_root = tmp_path / ".quodeq"
    monkeypatch.setenv("QUODEQ_HOME", str(quodeq_root))

    from quodeq._cli_evaluation import record_run_finished, record_run_started

    record_run_started(
        project="proj-x",
        run_id="r-1",
        branch="dev",
        model="claude-opus-4-7",
        db_path=str(tmp_path / "evaluations" / "proj-x" / "r-1" / "evaluation.db"),
    )
    runs = SqliteRunIndex(quodeq_root).list_runs(project="proj-x")
    assert len(runs) == 1
    assert runs[0].state == "running"
    assert runs[0].branch == "dev"
    assert runs[0].model == "claude-opus-4-7"

    record_run_finished(project="proj-x", run_id="r-1", state="completed")
    runs = SqliteRunIndex(quodeq_root).list_runs(project="proj-x")
    assert runs[0].state == "completed"
    assert runs[0].finished_at is not None


def test_record_run_started_handles_missing_branch_and_model(tmp_path: Path, monkeypatch):
    quodeq_root = tmp_path / ".quodeq"
    monkeypatch.setenv("QUODEQ_HOME", str(quodeq_root))

    from quodeq._cli_evaluation import record_run_started

    record_run_started(
        project="proj-y",
        run_id="r-2",
        branch=None,
        model=None,
        db_path=str(tmp_path / "x.db"),
    )
    runs = SqliteRunIndex(quodeq_root).list_runs(project="proj-y")
    assert len(runs) == 1
    assert runs[0].branch is None
    assert runs[0].model is None
