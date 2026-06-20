"""Tests for worktree cleanup on failure path (finding #376).

The except block in _create_worktree previously called worktree_dir.rmdir()
which only removes an empty dir and leaves a registered/populated worktree
behind. Fix: call _cleanup_worktree + shutil.rmtree on the failure path.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch, call

import pytest


class TestCreateWorktreeCleanupOnFailure:
    """Ensure _create_worktree fully cleans up on the failure path."""

    def test_cleanup_worktree_called_on_subprocess_failure(self, tmp_path: Path) -> None:
        """When subprocess.run raises CalledProcessError after the dir is created,
        _cleanup_worktree must be called (not just rmdir) so the git worktree
        registration is also removed."""
        from quodeq._cli_resolution import _create_worktree

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        captured_calls: list[tuple[Path, Path]] = []

        def _fake_cleanup(repo: Path, wt: Path) -> None:
            captured_calls.append((repo, wt))
            # Simulate cleanup removing the dir
            import shutil
            shutil.rmtree(wt, ignore_errors=True)

        with patch(
            "quodeq._cli_resolution.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ), patch(
            "quodeq._cli_resolution._cleanup_worktree",
            side_effect=_fake_cleanup,
        ) as mock_cleanup:
            result = _create_worktree(repo_dir, "some-branch")

        assert result is None, "Expected None when subprocess raises"
        # _cleanup_worktree must have been called once with the correct repo_dir
        mock_cleanup.assert_called_once()
        called_repo, called_wt = mock_cleanup.call_args.args
        assert called_repo == repo_dir

    def test_no_leftover_dir_on_failure(self, tmp_path: Path) -> None:
        """The worktree dir itself must not survive the failure path."""
        from quodeq._cli_resolution import _create_worktree

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        created_dir: list[Path] = []

        def _spy_cleanup(repo: Path, wt: Path) -> None:
            created_dir.append(wt)
            import shutil
            shutil.rmtree(wt, ignore_errors=True)

        with patch(
            "quodeq._cli_resolution.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ), patch(
            "quodeq._cli_resolution._cleanup_worktree",
            side_effect=_spy_cleanup,
        ):
            result = _create_worktree(repo_dir, "some-branch")

        assert result is None
        if created_dir:
            assert not created_dir[0].exists(), (
                f"Worktree dir {created_dir[0]} still exists after failure"
            )

    def test_cleanup_called_on_timeout(self, tmp_path: Path) -> None:
        """TimeoutExpired on the failure path also triggers proper cleanup."""
        from quodeq._cli_resolution import _create_worktree

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        with patch(
            "quodeq._cli_resolution.subprocess.run",
            side_effect=subprocess.TimeoutExpired("git", 30),
        ), patch(
            "quodeq._cli_resolution._cleanup_worktree",
        ) as mock_cleanup:
            result = _create_worktree(repo_dir, "some-branch")

        assert result is None
        mock_cleanup.assert_called_once()
