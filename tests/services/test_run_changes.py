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
