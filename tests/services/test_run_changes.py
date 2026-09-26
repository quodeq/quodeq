"""``changed_files`` scopes a diff to what moved between two commits."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from quodeq.services.run_changes import changed_files

_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@x"}


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                         text=True, env={**os.environ, **_ENV, "HOME": str(repo)})
    return out.stdout.strip()


def _repo_with_two_commits(repo: Path) -> tuple[str, str]:
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "a.py").write_text("a = 1\n", encoding="utf-8")
    (repo / "b.py").write_text("b = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "one")
    first = _git(repo, "rev-parse", "HEAD")
    (repo / "a.py").write_text("a = 2\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "two")
    return first, _git(repo, "rev-parse", "HEAD")


def test_changed_files_lists_only_touched_paths(tmp_path: Path) -> None:
    first, second = _repo_with_two_commits(tmp_path)
    assert changed_files(tmp_path, first, second) == {"a.py"}


def test_same_sha_is_an_empty_change_set(tmp_path: Path) -> None:
    first, _ = _repo_with_two_commits(tmp_path)
    assert changed_files(tmp_path, first, first) == set()


def test_no_repo_root_returns_none(tmp_path: Path) -> None:
    assert changed_files(None, "abc", "def") is None


def test_missing_sha_returns_none(tmp_path: Path) -> None:
    first, _ = _repo_with_two_commits(tmp_path)
    assert changed_files(tmp_path, None, first) is None


def test_unknown_sha_returns_none(tmp_path: Path) -> None:
    first, _ = _repo_with_two_commits(tmp_path)
    assert changed_files(tmp_path, "0" * 40, first) is None


def test_paths_are_relative_to_the_project_directory(tmp_path: Path) -> None:
    """A project registered one level below the repo root sees paths the way
    its findings spell them, and changes outside it are not in scope."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("o = 1\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "one")
    first = _git(tmp_path, "rev-parse", "HEAD")
    (pkg / "a.py").write_text("a = 2\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("o = 2\n", encoding="utf-8")
    _git(tmp_path, "commit", "-q", "-am", "two")
    second = _git(tmp_path, "rev-parse", "HEAD")
    assert changed_files(pkg, first, second) == {"a.py"}


def test_a_rename_lists_both_paths(tmp_path: Path) -> None:
    """Both the old and the new path are in scope, so the previous findings
    in the old file can resolve and the current ones can match by content."""
    first, _ = _repo_with_two_commits(tmp_path)
    _git(tmp_path, "mv", "b.py", "c.py")
    _git(tmp_path, "commit", "-q", "-m", "rename")
    third = _git(tmp_path, "rev-parse", "HEAD")
    assert {"b.py", "c.py"} <= changed_files(tmp_path, first, third)


def test_changed_files_is_memoized_per_commit_pair(tmp_path: Path) -> None:
    first, second = _repo_with_two_commits(tmp_path)
    changed_files.cache_clear()
    changed_files(tmp_path, first, second)
    changed_files(tmp_path, first, second)
    assert changed_files.cache_info().hits == 1
