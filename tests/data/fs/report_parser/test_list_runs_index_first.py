"""Verify list_runs prefers RunIndex when present, falls back to filesystem otherwise."""
from pathlib import Path

from quodeq.data.fs.report_parser.runs import list_runs
from quodeq.data.sqlite.index_repository import SqliteRunIndex


def test_list_runs_uses_index_when_present(tmp_path: Path, monkeypatch):
    quodeq_root = tmp_path / ".quodeq"
    quodeq_root.mkdir()
    monkeypatch.setenv("QUODEQ_HOME", str(quodeq_root))

    idx = SqliteRunIndex(quodeq_root)
    idx.record_started(
        project="p",
        run_id="r1",
        branch=None,
        model="m",
        started_at="2026-04-29T10:00:00Z",
        db_path=str(tmp_path / "p" / "r1" / "evaluation.db"),
    )

    reports_root = tmp_path / "evaluations"
    reports_root.mkdir()
    runs = list_runs(reports_root, "p")
    assert [r.run_id for r in runs] == ["r1"]
    assert runs[0].status == "in_progress"  # state="running" maps to "in_progress"


def test_list_runs_index_state_completed_maps_to_complete(tmp_path: Path, monkeypatch):
    quodeq_root = tmp_path / ".quodeq"
    quodeq_root.mkdir()
    monkeypatch.setenv("QUODEQ_HOME", str(quodeq_root))

    idx = SqliteRunIndex(quodeq_root)
    idx.record_started(
        project="p",
        run_id="r1",
        branch="main",
        model="m",
        started_at="2026-04-29T10:00:00Z",
        db_path="/x/r1/evaluation.db",
    )
    idx.record_finished(
        project="p", run_id="r1", finished_at="2026-04-29T10:05:00Z", state="completed",
    )

    reports_root = tmp_path / "evaluations"
    reports_root.mkdir()
    runs = list_runs(reports_root, "p")
    assert runs[0].status == "complete"
    assert runs[0].branch == "main"


def test_list_runs_falls_back_to_filesystem_when_no_index(tmp_path: Path, monkeypatch):
    """When index.db doesn't exist, fall back to filesystem scan."""
    monkeypatch.setenv("QUODEQ_HOME", str(tmp_path / "no-index"))
    reports_root = tmp_path / "evaluations"
    run_dir = reports_root / "p" / "20260429T120000"
    (run_dir / "evidence").mkdir(parents=True)
    # Filesystem scan needs manifest.json to count the run
    (run_dir / "evidence" / "manifest.json").write_text("{}")
    runs = list_runs(reports_root, "p")
    assert any(r.run_id == "20260429T120000" for r in runs)


def test_list_runs_falls_back_to_filesystem_when_index_empty(tmp_path: Path, monkeypatch):
    """When index.db exists but has no rows for this project, fall back to filesystem."""
    quodeq_root = tmp_path / ".quodeq"
    quodeq_root.mkdir()
    monkeypatch.setenv("QUODEQ_HOME", str(quodeq_root))
    # Force creation of index.db without any runs by listing first
    SqliteRunIndex(quodeq_root).list_runs(project="other-project")

    reports_root = tmp_path / "evaluations"
    run_dir = reports_root / "p" / "20260429T120000"
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}")
    runs = list_runs(reports_root, "p")
    assert any(r.run_id == "20260429T120000" for r in runs)
