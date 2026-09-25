"""remove_run_directory outcomes: fast path, scan fallback, and a directory that will not go."""
from __future__ import annotations

from pathlib import Path

from quodeq.data.fs import run_dirs
from quodeq.data.fs.run_dirs import remove_run_directory


class _Log:
    """A LogSink that keeps the warnings."""

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def info(self, message: str) -> None: ...
    def debug(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...
    def success(self, message: str) -> None: ...


def _run(tmp_path: Path, project: str = "proj") -> tuple[Path, Path]:
    reports = tmp_path / "reports"
    run = reports / project / "run1"
    run.mkdir(parents=True)
    return reports, run


def test_the_known_project_dir_is_removed(tmp_path):
    reports, run = _run(tmp_path)
    log = _Log()
    assert remove_run_directory(reports, "proj", "run1", log=log) is True
    assert not run.exists()
    assert log.warnings == []


def test_a_wrong_project_falls_back_to_the_scan(tmp_path):
    reports, run = _run(tmp_path)
    log = _Log()
    assert remove_run_directory(reports, "other", "run1", log=log) is True
    assert not run.exists()
    assert log.warnings == []


def test_no_match_removes_nothing(tmp_path):
    reports, _ = _run(tmp_path)
    log = _Log()
    assert remove_run_directory(reports, None, "run2", log=log) is False
    assert log.warnings == []


def test_a_directory_that_survives_rmtree_is_warned_on_each_attempt(tmp_path, monkeypatch):
    reports, run = _run(tmp_path)
    monkeypatch.setattr(run_dirs.shutil, "rmtree", lambda *a, **k: None)
    log = _Log()
    assert remove_run_directory(reports, "proj", "run1", log=log) is False
    # The fast path fails, then the scan finds the same directory and tries again.
    assert log.warnings == [f"Could not remove run directory {run}"] * 2


def test_a_scan_hit_that_survives_rmtree_is_warned_once(tmp_path, monkeypatch):
    reports, run = _run(tmp_path)
    monkeypatch.setattr(run_dirs.shutil, "rmtree", lambda *a, **k: None)
    log = _Log()
    assert remove_run_directory(reports, None, "run1", log=log) is False
    assert log.warnings == [f"Could not remove run directory {run}"]
