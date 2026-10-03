"""refresh_working_copy against real temp git repositories."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from quodeq.core.types.working_copy_refresh import RefreshOutcome
from quodeq.data.fs.repo_refresh import refresh_working_copy

_GIT_IDENTITY = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *_GIT_IDENTITY, *args], cwd=cwd, check=True, capture_output=True, text=True,
        stdin=subprocess.DEVNULL,
    )
    return proc.stdout.strip()


def _commit(repo: Path, name: str, content: str = "x") -> None:
    (repo / name).write_text(content, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-m", f"add {name}")


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    """An upstream repository with one commit on ``main``."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-b", "main")
    _commit(upstream, "a.txt")
    return upstream


@pytest.fixture
def clone(tmp_path: Path, remote: Path) -> Path:
    dest = tmp_path / "clone"
    _git(tmp_path, "clone", str(remote), str(dest))
    return dest


def test_fast_forwards_and_counts_new_commits(remote: Path, clone: Path) -> None:
    _commit(remote, "b.txt")
    _commit(remote, "c.txt")

    result = refresh_working_copy(clone, hard_reset=False)

    assert result.outcome == RefreshOutcome.UPDATED
    assert result.new_commits == 2
    assert (clone / "c.txt").exists()
    assert _git(clone, "rev-parse", "HEAD") == _git(remote, "rev-parse", "HEAD")


def test_already_up_to_date(clone: Path) -> None:
    result = refresh_working_copy(clone, hard_reset=False)

    assert result.outcome == RefreshOutcome.UP_TO_DATE
    assert result.new_commits == 0


def test_dirty_tree_is_refused_untouched(remote: Path, clone: Path) -> None:
    _commit(remote, "b.txt")
    (clone / "a.txt").write_text("local edit", encoding="utf-8")

    result = refresh_working_copy(clone, hard_reset=False)

    assert result.outcome == RefreshOutcome.DIRTY
    assert (clone / "a.txt").read_text(encoding="utf-8") == "local edit"
    assert not (clone / "b.txt").exists()


def test_diverged_history_is_refused(remote: Path, clone: Path) -> None:
    _commit(remote, "b.txt")
    _commit(clone, "local.txt")
    head_before = _git(clone, "rev-parse", "HEAD")

    result = refresh_working_copy(clone, hard_reset=False)

    assert result.outcome == RefreshOutcome.DIVERGED
    assert _git(clone, "rev-parse", "HEAD") == head_before


def test_branch_without_upstream_is_refused(clone: Path) -> None:
    _git(clone, "checkout", "-b", "feature")

    result = refresh_working_copy(clone, hard_reset=False)

    assert result.outcome == RefreshOutcome.NO_UPSTREAM


def test_hard_reset_follows_a_force_push(remote: Path, clone: Path) -> None:
    _commit(remote, "b.txt")
    refresh_working_copy(clone, hard_reset=True)
    _git(remote, "reset", "--hard", "HEAD~1")
    _commit(remote, "rewritten.txt")

    result = refresh_working_copy(clone, hard_reset=True)

    assert result.outcome == RefreshOutcome.UPDATED
    assert (clone / "rewritten.txt").exists()
    assert not (clone / "b.txt").exists()
    assert _git(clone, "rev-parse", "HEAD") == _git(remote, "rev-parse", "HEAD")


def test_hard_reset_discards_local_modifications(clone: Path) -> None:
    (clone / "a.txt").write_text("stray edit", encoding="utf-8")

    result = refresh_working_copy(clone, hard_reset=True)

    assert result.outcome == RefreshOutcome.UP_TO_DATE
    assert (clone / "a.txt").read_text(encoding="utf-8") == "x"


def test_shallow_single_branch_clone_updates(tmp_path: Path, remote: Path) -> None:
    dest = tmp_path / "shallow"
    _git(tmp_path, "clone", "--single-branch", "--no-tags", "--depth", "1", remote.as_uri(), str(dest))
    _commit(remote, "b.txt")

    result = refresh_working_copy(dest, hard_reset=True)

    assert result.outcome == RefreshOutcome.UPDATED
    assert (dest / "b.txt").exists()


def test_unreachable_remote_reports_fetch_failure(tmp_path: Path, clone: Path) -> None:
    _git(clone, "remote", "set-url", "origin", str(tmp_path / "gone"))

    result = refresh_working_copy(clone, hard_reset=False)

    assert result.outcome == RefreshOutcome.FETCH_FAILED
    assert result.detail
