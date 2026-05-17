# tests/services/test_filesystem_log_resolution.py
"""FilesystemActionProvider.get_log_run_dir / is_job_complete."""
from __future__ import annotations

from pathlib import Path

from quodeq.services.filesystem import FilesystemActionProvider


def test_get_log_run_dir_external_run(tmp_path: Path) -> None:
    """Given an ext-<run_id> job_id, scans reports_root for a matching run."""
    project = tmp_path / "proj-1"
    run = project / "run-A"
    run.mkdir(parents=True)
    (run / "evidence").mkdir()
    provider = FilesystemActionProvider(reports_root=tmp_path)
    assert provider.get_log_run_dir("ext-run-A") == run


def test_get_log_run_dir_external_not_found(tmp_path: Path) -> None:
    provider = FilesystemActionProvider(reports_root=tmp_path)
    assert provider.get_log_run_dir("ext-run-nonexistent") is None


def test_get_log_run_dir_bare_run_id_falls_back_to_filesystem(tmp_path: Path) -> None:
    """A bare run_id (no ext- prefix, no job entry) must still resolve.

    The UI subscribes to the per-run SSE stream using the plain run UUID. For
    completed runs without an active job entry, falling back to a filesystem
    scan keeps live-grade updates working.
    """
    project = tmp_path / "proj-1"
    run = project / "run-A"
    run.mkdir(parents=True)
    (run / "evidence").mkdir()
    provider = FilesystemActionProvider(reports_root=tmp_path)
    assert provider.get_log_run_dir("run-A") == run


def test_get_log_run_dir_bare_run_id_unknown_returns_none(tmp_path: Path) -> None:
    provider = FilesystemActionProvider(reports_root=tmp_path)
    assert provider.get_log_run_dir("run-nonexistent") is None


def test_is_job_complete_external_when_scan_present(tmp_path: Path) -> None:
    project = tmp_path / "p"
    run = project / "r"
    run.mkdir(parents=True)
    (run / "scan.json").write_text("{}")
    provider = FilesystemActionProvider(reports_root=tmp_path)
    assert provider.is_job_complete("ext-r") is True


def test_is_job_complete_external_when_scan_absent(tmp_path: Path) -> None:
    """A run with a live .pid and no scan.json is still in progress (not complete)."""
    import os
    project = tmp_path / "p"
    run = project / "r"
    run.mkdir(parents=True)
    # Live PID present -> genuinely running -> not complete
    (run / ".pid").write_text(str(os.getpid()))
    provider = FilesystemActionProvider(reports_root=tmp_path)
    assert provider.is_job_complete("ext-r") is False


def test_is_job_complete_external_stale_pid(tmp_path: Path) -> None:
    """Stale ext- run (no scan.json, dead PID) should be treated as complete.

    Otherwise the SSE endpoint tails the log forever waiting for a scan.json
    that will never arrive.
    """
    project = tmp_path / "p"
    run = project / "r"
    (run / "evidence").mkdir(parents=True)
    (run / "evidence" / "manifest.json").write_text("{}")
    (run / ".pid").write_text("999999999")
    provider = FilesystemActionProvider(reports_root=tmp_path)
    assert provider.is_job_complete("ext-r") is True
