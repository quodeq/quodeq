"""Tests for --branch and --scope CLI argument handling."""

from __future__ import annotations

import json
import subprocess
import os
from pathlib import Path

import pytest


def _make_git_repo(path: Path, branches: list[str] | None = None) -> None:
    """Create a minimal git repo with optional extra branches."""
    env = {
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t",
        "HOME": str(path),
        "PATH": os.environ["PATH"],
    }
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "checkout", "-b", "main"], capture_output=True, check=True)
    (path / "README.md").write_text("# test")
    (path / "src").mkdir()
    (path / "src" / "app.py").write_text("print('hello')")
    subprocess.run(["git", "-C", str(path), "add", "."], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "init"], capture_output=True, check=True, env=env)
    for branch in (branches or []):
        subprocess.run(["git", "-C", str(path), "checkout", "-b", branch], capture_output=True, check=True)
        (path / "branch_file.txt").write_text(f"from {branch}")
        subprocess.run(["git", "-C", str(path), "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(path), "commit", "-m", f"commit on {branch}"], capture_output=True, check=True, env=env)
    subprocess.run(["git", "-C", str(path), "checkout", "main"], capture_output=True, check=True)


class TestCreateWorktree:
    def test_creates_worktree_for_branch(self, tmp_path: Path) -> None:
        from quodeq.cli import _create_worktree
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_git_repo(repo, branches=["feature/test"])

        wt = _create_worktree(repo, "feature/test")
        try:
            assert wt is not None
            assert wt.is_dir()
            assert (wt / "branch_file.txt").exists()
            assert (wt / "branch_file.txt").read_text() == "from feature/test"
        finally:
            # Clean up even if assertions fail
            if wt is not None:
                subprocess.run(["git", "-C", str(repo), "worktree", "remove", str(wt), "--force"], capture_output=True)

    def test_returns_none_for_nonexistent_branch(self, tmp_path: Path) -> None:
        from quodeq.cli import _create_worktree
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_git_repo(repo)

        wt = _create_worktree(repo, "nonexistent-branch")
        assert wt is None

    def test_fetches_missing_branch_from_origin(self, tmp_path: Path) -> None:
        """Online repos are registered via a single-branch shallow clone, so a
        branch evaluation targets a branch the clone doesn't have yet; it must
        be fetched from origin instead of failing."""
        from quodeq.cli import _create_worktree
        origin = tmp_path / "origin"
        origin.mkdir()
        _make_git_repo(origin, branches=["feature/other"])
        clone = tmp_path / "clone"
        subprocess.run(
            ["git", "clone", "--single-branch", "--branch", "main", str(origin), str(clone)],
            capture_output=True, check=True,
        )

        wt = _create_worktree(clone, "feature/other")
        try:
            assert wt is not None
            assert (wt / "branch_file.txt").read_text() == "from feature/other"
        finally:
            if wt is not None:
                subprocess.run(["git", "-C", str(clone), "worktree", "remove", str(wt), "--force"], capture_output=True)


class TestCleanupWorktree:
    def test_removes_worktree(self, tmp_path: Path) -> None:
        from quodeq.cli import _create_worktree, _cleanup_worktree
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_git_repo(repo, branches=["feature/cleanup"])

        wt = _create_worktree(repo, "feature/cleanup")
        assert wt is not None
        assert wt.is_dir()

        _cleanup_worktree(repo, wt)
        assert not wt.exists()


class TestCliParserBranchScope:
    def test_branch_arg_parsed(self) -> None:
        from quodeq.cli_parser import build_parser
        parser = build_parser()
        args = parser.parse_args(["evaluate", "/tmp/repo", "--branch", "develop"])
        assert args.branch == "develop"

    def test_scope_arg_parsed(self) -> None:
        from quodeq.cli_parser import build_parser
        parser = build_parser()
        args = parser.parse_args(["evaluate", "/tmp/repo", "--scope", "src/backend"])
        assert args.scope == "src/backend"

    def test_defaults_are_none(self) -> None:
        from quodeq.cli_parser import build_parser
        parser = build_parser()
        args = parser.parse_args(["evaluate", "/tmp/repo"])
        assert args.branch is None
        assert args.scope is None
