"""Local git repository statistics.

A read-only ``git`` subprocess call over an analyzed repo's history, and
plain reads of ``.git`` files. Fails open (returns None) on any git or file
trouble -- a missing repo, no git binary, a non-zero exit, a timeout -- so
a staleness signal can never crash the caller that asks for it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from quodeq.shared.win_launch import program_argv

_DEFAULT_TIMEOUT_S = 5


def count_commits_since(
    repo_root: Path, since_iso: str, *, timeout_s: int = _DEFAULT_TIMEOUT_S,
) -> int | None:
    """Commits in *repo_root* since *since_iso*, or None when unknowable.

    None (never 0 as a stand-in) on any git trouble: a missing repo, no git
    binary, a non-zero exit, a timeout, or an unparseable count. Callers must
    not infer "no new commits" from a None result.
    """
    try:
        proc = subprocess.run(
            program_argv(["git", "-C", str(repo_root), "rev-list", "--count", f"--since={since_iso}", "HEAD"]),
            capture_output=True, encoding="utf-8", timeout=timeout_s, check=False,
        )
        if proc.returncode != 0:
            return None
        return int(proc.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def last_fetched_mtime(repo: Path) -> float | None:
    """Mtime of *repo*'s ``.git/FETCH_HEAD``, or ``.git/HEAD`` as fallback.

    None when neither file exists, or when the one that does is unstatable
    (permissions, a race with deletion). Callers convert the raw mtime to
    whatever presentation format (ISO string, relative age) they need.
    """
    fetch_head = repo / ".git" / "FETCH_HEAD"
    head = repo / ".git" / "HEAD"
    candidate = fetch_head if fetch_head.exists() else head if head.exists() else None
    if candidate is None:
        return None
    try:
        return candidate.stat().st_mtime
    except OSError:
        return None


# Which branch a working copy has checked out. The project list asks this
# for every local row on each rebuild, so it reads two small files instead
# of spawning git. It follows a linked worktree's .git file to its own HEAD
# and walks up from a scoped subfolder to the repository it sits in.
_GIT_DIR_NAME = ".git"
_GITDIR_PREFIX = "gitdir:"
_HEAD_FILE = "HEAD"
_REF_PREFIX = "ref: refs/heads/"
_SHORT_SHA_LEN = 7


def _git_dir(start: Path) -> Path | None:
    """The git directory for *start* or the nearest folder above it."""
    for folder in (start, *start.parents):
        marker = folder / _GIT_DIR_NAME
        if marker.is_dir():
            return marker
        if marker.is_file():
            target = marker.read_text(encoding="utf-8").strip()
            if not target.startswith(_GITDIR_PREFIX):
                return None
            gitdir = Path(target[len(_GITDIR_PREFIX):].strip())
            return gitdir if gitdir.is_absolute() else folder / gitdir
    return None


def checked_out_branch(path: str | None) -> str | None:
    """The branch checked out at *path*, the short sha on a detached HEAD,
    or None when *path* is not inside a git working copy."""
    if not path:
        return None
    try:
        git_dir = _git_dir(Path(path))
        if git_dir is None:
            return None
        head = (git_dir / _HEAD_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if head.startswith(_REF_PREFIX):
        return head[len(_REF_PREFIX):] or None
    return head[:_SHORT_SHA_LEN] or None
