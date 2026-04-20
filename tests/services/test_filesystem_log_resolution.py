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


def test_is_job_complete_external_when_scan_present(tmp_path: Path) -> None:
    project = tmp_path / "p"
    run = project / "r"
    run.mkdir(parents=True)
    (run / "scan.json").write_text("{}")
    provider = FilesystemActionProvider(reports_root=tmp_path)
    assert provider.is_job_complete("ext-r") is True


def test_is_job_complete_external_when_scan_absent(tmp_path: Path) -> None:
    project = tmp_path / "p"
    run = project / "r"
    run.mkdir(parents=True)
    provider = FilesystemActionProvider(reports_root=tmp_path)
    assert provider.is_job_complete("ext-r") is False
