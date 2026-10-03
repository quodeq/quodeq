"""Bring a registered project's working copy up to date with its remote.

Two endings after the same fetch. A clone quodeq manages (nobody edits it)
is hard-reset onto the fetched commit, which also follows a force-push. Any
other checkout belongs to the user: it only ever fast-forwards, and only
from a clean tree, so no local work can be lost.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from quodeq.core.types.working_copy_refresh import RefreshOutcome
from quodeq.data.fs.shared_repo_git import run_git
from quodeq.shared.git_errors import output_tail

_REMOTE = "origin"
_UPSTREAM_PREFIX = f"{_REMOTE}/"
_REV_PARSE = "rev-parse"
# Seconds; local plumbing (rev-parse, status, merge, reset) on one repo.
_LOCAL_TIMEOUT_S = 30


@dataclass(frozen=True)
class RefreshResult:
    """*new_commits* counts what an UPDATED refresh brought in; *detail* is
    the failing git command's output tail."""

    outcome: RefreshOutcome
    new_commits: int = 0
    detail: str = ""


def _local(repo: Path, *args: str) -> tuple[bool, str]:
    ok, out = run_git(list(args), cwd=repo, timeout=_LOCAL_TIMEOUT_S)
    return ok, out.strip()


def _upstream_branch(repo: Path) -> str | None:
    """The origin branch the checked-out branch tracks, or None (detached
    HEAD, no upstream, an upstream on another remote)."""
    ok, out = _local(repo, _REV_PARSE, "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if not ok or not out.startswith(_UPSTREAM_PREFIX):
        return None
    return out[len(_UPSTREAM_PREFIX):] or None


def _is_dirty(repo: Path) -> bool:
    """True when tracked files differ from HEAD, or when that cannot be told."""
    ok, out = _local(repo, "status", "--porcelain", "--untracked-files=no")
    return not ok or bool(out)


def _count_behind(repo: Path, tracking_ref: str) -> int:
    ok, out = _local(repo, "rev-list", "--count", f"HEAD..{tracking_ref}")
    return int(out) if ok and out.isdigit() else 0


def refresh_working_copy(
    repo: Path, *, hard_reset: bool, timeout_s: int = _LOCAL_TIMEOUT_S,
    env: Mapping[str, str] | None = None, git_config: Sequence[str] = (),
) -> RefreshResult:
    """Fetch the tracked origin branch into *repo* and move the checkout onto it.

    *hard_reset* picks the ending (see the module docstring). *timeout_s*
    bounds the fetch, the only network step; *env* and *git_config*
    (``key=value`` entries passed as ``-c``) apply to it alone.
    """
    branch = _upstream_branch(repo)
    if branch is None:
        return RefreshResult(RefreshOutcome.NO_UPSTREAM)
    if not hard_reset and _is_dirty(repo):
        return RefreshResult(RefreshOutcome.DIRTY)

    tracking_ref = f"refs/remotes/{_REMOTE}/{branch}"
    config_flags = [flag for entry in git_config for flag in ("-c", entry)]
    ok, out = run_git(
        [*config_flags, "fetch", _REMOTE, f"+refs/heads/{branch}:{tracking_ref}"],
        cwd=repo, timeout=timeout_s, env=env,
    )
    if not ok:
        return RefreshResult(RefreshOutcome.FETCH_FAILED, detail=output_tail(out))

    _, before = _local(repo, _REV_PARSE, "HEAD")
    new_commits = _count_behind(repo, tracking_ref)
    if hard_reset:
        ok, out = _local(repo, "reset", "--hard", tracking_ref)
    elif new_commits == 0:
        return RefreshResult(RefreshOutcome.UP_TO_DATE)
    else:
        ok, out = _local(repo, "merge", "--ff-only", tracking_ref)
    if not ok:
        return RefreshResult(RefreshOutcome.DIVERGED, detail=output_tail(out))
    _, after = _local(repo, _REV_PARSE, "HEAD")
    if after == before:
        return RefreshResult(RefreshOutcome.UP_TO_DATE)
    return RefreshResult(RefreshOutcome.UPDATED, new_commits=new_commits)
