"""Git worktree management for branch-scoped evaluation.

Split from ``_cli_resolution.py`` to keep each module under 300 lines.
Re-exported by ``_cli_resolution.py`` (which is in turn re-exported by
``_cli_evaluation.py``), so existing ``quodeq._cli_resolution.<name>`` and
``quodeq._cli_evaluation.<name>`` patch targets keep working unchanged.

``_create_worktree``'s failure path calls ``_cleanup_worktree`` through a
deferred lookup on ``quodeq._cli_resolution`` (rather than a bare name)
because tests patch ``quodeq._cli_resolution._cleanup_worktree`` directly —
see ``tests/test_cli_worktree_cleanup.py``. ``_fetch_branch`` looks up its
timeout the same way: ``_FETCH_TIMEOUT_S`` stays defined in
``_cli_resolution.py`` because a test reloads that module
(``importlib.reload``) with ``QUODEQ_GIT_CLONE_TIMEOUT_S`` set and reads the
import-time constant back off it — see
``tests/services/test_env_fallbacks.py::test_fetch_timeout_invalid_falls_back``.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile as _tempfile
from pathlib import Path

_logger = logging.getLogger(__name__)

_WORKTREE_TIMEOUT_S = 30


def _fetch_branch(repo_dir: Path, branch: str) -> bool:
    """Fetch *branch* from origin into a local branch of the same name.

    Single-branch clones (online repos registered via run_git_clone) have no
    refspec for other branches, so a plain ``fetch origin <branch>`` would
    only update FETCH_HEAD; the explicit ``<branch>:<branch>`` refspec makes
    it usable by ``worktree add``. Returns True when the fetch succeeded.
    """
    from quodeq import _cli_resolution as _facade
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "fetch", "origin", f"{branch}:{branch}"],
            capture_output=True, text=True, encoding="utf-8", timeout=_facade._FETCH_TIMEOUT_S,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _create_worktree(repo_dir: Path, branch: str) -> Path | None:
    """Create a temporary git worktree for the given branch.

    Returns the worktree path, or None on failure. When the first attempt
    fails, the branch is fetched from origin and the attempt repeated once:
    single-branch clones (online repos) don't have other branches locally
    until someone asks for them.
    """
    worktree_dir = Path(_tempfile.mkdtemp(prefix=f"quodeq-wt-{branch.replace('/', '-')}-"))
    from quodeq import _cli_resolution as _facade
    for retried in (False, True):
        try:
            subprocess.run(
                ["git", "-C", str(repo_dir), "worktree", "add", str(worktree_dir), branch],
                capture_output=True, text=True, encoding="utf-8", check=True, timeout=_WORKTREE_TIMEOUT_S,
            )
            return worktree_dir
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            if not retried and _fetch_branch(repo_dir, branch):
                continue
            print(f"Failed to create worktree for branch '{branch}': {exc}", file=sys.stderr)
            _facade._cleanup_worktree(repo_dir, worktree_dir)
            shutil.rmtree(worktree_dir, ignore_errors=True)
            return None
    return None


def _cleanup_worktree(repo_dir: Path, worktree_dir: Path) -> None:
    """Remove a temporary git worktree."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "worktree", "remove", str(worktree_dir), "--force"],
            capture_output=True, text=True, encoding="utf-8", timeout=_WORKTREE_TIMEOUT_S,
        )
        if result.returncode != 0:
            _logger.warning(
                "git worktree remove %s exited %d: %s",
                worktree_dir, result.returncode, (result.stderr or "").strip(),
            )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        _logger.debug("Failed to clean up worktree %s: %s", worktree_dir, exc)
