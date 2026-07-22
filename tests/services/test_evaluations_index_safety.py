"""Safety fixes on EvaluationsIndex: id validation and honest delete results.

Covers SEC-05 (traversal ``ext-`` ids never reach path construction in
``get_status``) and REL-026/REL-027 (``delete`` reports failure when the run
directory survives ``rmtree``).
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from quodeq.services._evaluations_index import EvaluationsIndex
from quodeq.services._job_model import InMemoryJobStore
from quodeq.services.jobs import JobManager
from quodeq.shared.run_status import RunState, write_status


def _make_index(tmp_path: Path, reports_root: Path) -> EvaluationsIndex:
    jobs = JobManager(job_store=InMemoryJobStore(), reports_root=reports_root)
    return EvaluationsIndex(
        jobs=jobs,
        index_db_path=tmp_path / "index.db",
        reports_root=reports_root,
    )


def _seed_terminal_run(reports_root: Path, project: str, run_id: str) -> Path:
    run_dir = reports_root / project / run_id
    run_dir.mkdir(parents=True)
    write_status(
        run_dir,
        state=RunState.FAILED,
        job_id=f"ext-{run_id}",
        started_at="2026-05-22T19:00:00+00:00",
        dimensions=["security"],
        phase="done",
        pid=99999,
    )
    return run_dir


def test_get_status_rejects_traversal_ext_id(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    _seed_terminal_run(reports_root, "proj-a", "run-a")
    index = _make_index(tmp_path, reports_root)

    assert index.get_status("ext-..", reports_dir=reports_root) is None
    assert index.get_status("ext-.", reports_dir=reports_root) is None
    assert index.get_status("ext-", reports_dir=reports_root) is None


def test_get_status_still_resolves_valid_ext_id(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    _seed_terminal_run(reports_root, "proj-a", "run-a")
    index = _make_index(tmp_path, reports_root)

    snapshot = index.get_status("ext-run-a", reports_dir=reports_root)
    assert snapshot is not None
    assert snapshot.output_run_id == "run-a"


def test_delete_reports_failure_when_dir_survives(tmp_path, monkeypatch, caplog) -> None:
    reports_root = tmp_path / "reports"
    run_dir = _seed_terminal_run(reports_root, "proj-a", "run-a")
    index = _make_index(tmp_path, reports_root)

    # Simulate a deletion that silently fails (e.g. Windows file locks):
    # ignore_errors=True means rmtree itself never raises.
    monkeypatch.setattr(shutil, "rmtree", lambda *a, **k: None)

    with caplog.at_level(logging.WARNING, logger="quodeq.services._evaluations_index"):
        assert index.delete("ext-run-a", reports_dir=reports_root) is False
    assert run_dir.is_dir()
    assert "Could not remove run directory" in caplog.text


def test_delete_reports_success_when_dir_removed(tmp_path) -> None:
    reports_root = tmp_path / "reports"
    run_dir = _seed_terminal_run(reports_root, "proj-a", "run-a")
    index = _make_index(tmp_path, reports_root)

    assert index.delete("ext-run-a", reports_dir=reports_root) is True
    assert not run_dir.exists()
