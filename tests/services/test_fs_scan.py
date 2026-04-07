"""Tests for the quick-scan service."""

from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.types.scan import ScanData


def _make_git_repo(path: Path) -> None:
    """Create a minimal git repo with two branches."""
    import subprocess
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "checkout", "-b", "main"], capture_output=True, check=True)
    (path / "README.md").write_text("# test")
    subprocess.run(["git", "-C", str(path), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "init"],
        capture_output=True, check=True,
        env={"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(path), "PATH": __import__("os").environ["PATH"]},
    )
    subprocess.run(["git", "-C", str(path), "checkout", "-b", "feature/foo"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "checkout", "main"], capture_output=True, check=True)


def test_scan_project_collects_files(tmp_path: Path) -> None:
    """Scan should list all files and count them."""
    from quodeq.services._fs_scan import scan_project
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    (project_dir / "app.py").write_text("print('hi')")
    (project_dir / "utils.py").write_text("pass")
    (project_dir / "README.md").write_text("# docs")
    result = scan_project(project_dir)
    assert isinstance(result, ScanData)
    assert result.total_files == 3
    assert "app.py" in result.file_tree
    assert result.languages.get("py") == 2
    assert result.languages.get("md") == 1


def test_scan_project_lists_branches(tmp_path: Path) -> None:
    """Scan should detect git branches."""
    from quodeq.services._fs_scan import scan_project
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    _make_git_repo(project_dir)
    result = scan_project(project_dir)
    assert "main" in result.branches
    assert "feature/foo" in result.branches


def test_scan_project_detects_modules(tmp_path: Path) -> None:
    """Scan should list top-level directories as modules."""
    from quodeq.services._fs_scan import scan_project
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    (project_dir / "src").mkdir()
    (project_dir / "src" / "main.py").write_text("pass")
    (project_dir / "tests").mkdir()
    (project_dir / "tests" / "test_main.py").write_text("pass")
    result = scan_project(project_dir)
    assert "src" in result.modules
    assert "tests" in result.modules


def test_scan_project_writes_json(tmp_path: Path) -> None:
    """Scan should write scan.json to reports directory when given one."""
    from quodeq.services._fs_scan import scan_project
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    (project_dir / "app.py").write_text("pass")
    reports_dir = tmp_path / "reports" / "project-123"
    reports_dir.mkdir(parents=True)
    result = scan_project(project_dir, output_dir=reports_dir)
    scan_file = reports_dir / "scan.json"
    assert scan_file.exists()
    data = json.loads(scan_file.read_text())
    assert data["total_files"] == 1
    assert data["scanned_at"] == result.scanned_at


def test_scan_project_no_git(tmp_path: Path) -> None:
    """Scan should work without a git repo — branches list empty."""
    from quodeq.services._fs_scan import scan_project
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    (project_dir / "main.py").write_text("pass")
    result = scan_project(project_dir)
    assert result.branches == []
    assert result.total_files == 1
