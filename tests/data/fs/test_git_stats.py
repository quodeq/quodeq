"""last_fetched_mtime: prefers FETCH_HEAD, falls back to HEAD, else None."""
from __future__ import annotations

import os
import time
from pathlib import Path

from quodeq.data.fs.git_stats import last_fetched_mtime


def test_prefers_fetch_head_over_head_when_both_present(tmp_path: Path):
    repo = tmp_path / "repo"
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)
    head = git_dir / "HEAD"
    fetch_head = git_dir / "FETCH_HEAD"
    head.write_text("ref: refs/heads/main\n")
    fetch_head.write_text("abc123\n")

    older = time.time() - 100
    newer = time.time()
    os.utime(head, (older, older))
    os.utime(fetch_head, (newer, newer))

    result = last_fetched_mtime(repo)

    assert result == fetch_head.stat().st_mtime
    assert result != head.stat().st_mtime


def test_falls_back_to_head_when_fetch_head_absent(tmp_path: Path):
    repo = tmp_path / "repo"
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)
    head = git_dir / "HEAD"
    head.write_text("ref: refs/heads/main\n")

    result = last_fetched_mtime(repo)

    assert result == head.stat().st_mtime


def test_none_when_neither_file_present(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)

    assert last_fetched_mtime(repo) is None


def test_none_when_repo_has_no_git_dir(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()

    assert last_fetched_mtime(repo) is None
