"""Tests for resolve_diff_files."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from quodeq.analysis._diff_resolver import DiffResolveError, resolve_diff_files


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True)


def _init_repo_with_base_and_changes(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "t@t"], repo)
    _run(["git", "config", "user.name", "t"], repo)
    (repo / "keep.py").write_text("a = 1\n")
    (repo / "drop.py").write_text("b = 2\n")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-q", "-m", "base"], repo)
    _run(["git", "checkout", "-q", "-b", "feature"], repo)
    (repo / "new.py").write_text("c = 3\n")
    (repo / "keep.py").write_text("a = 99\n")
    (repo / "drop.py").unlink()
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-q", "-m", "change"], repo)
    return repo


def test_returns_added_and_modified_files(tmp_path: Path) -> None:
    repo = _init_repo_with_base_and_changes(tmp_path)
    result = resolve_diff_files(repo, "main")
    assert set(result) == {"new.py", "keep.py"}


def test_drops_deleted_files(tmp_path: Path) -> None:
    repo = _init_repo_with_base_and_changes(tmp_path)
    result = resolve_diff_files(repo, "main")
    assert "drop.py" not in result


def test_empty_diff_returns_empty_list(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "t@t"], repo)
    _run(["git", "config", "user.name", "t"], repo)
    (repo / "f.py").write_text("x = 1\n")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-q", "-m", "only"], repo)
    result = resolve_diff_files(repo, "main")
    assert result == []


def test_unknown_ref_raises_diff_resolve_error(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "t@t"], repo)
    _run(["git", "config", "user.name", "t"], repo)
    (repo / "f.py").write_text("x = 1\n")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-q", "-m", "c"], repo)
    with pytest.raises(DiffResolveError):
        resolve_diff_files(repo, "does-not-exist")
