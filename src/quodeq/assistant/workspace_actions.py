"""Apply / PR-create / discard workspace workflows, extracted from the HTTP
routes that expose them.

Integration is HUMAN-ONLY (see assistant_workspace_routes.py). These
functions are framework-free: turn claim/release come in as callables so
this module carries no Flask dependency. Each one claims the per-session
turn slot, re-reads the worktree row under the claim (state may have moved
since the route's initial lookup), runs the git operation, advances the row
status, and always releases the slot. The route only translates the
returned Outcome to its frozen HTTP response body -- including the
curated-error behavior added in #1152/#1153: a WorktreeError's raw text is
returned in ``detail`` for the route to log server-side, never surfaced to
the client directly.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from quodeq.assistant.worktree import WorktreeError, WorktreeManager
from quodeq.data.ports.assistant import AssistantStore

_logger = logging.getLogger(__name__)

ClaimTurn = Callable[[str], bool]
ReleaseTurn = Callable[[str], None]


def _manager(row: dict) -> WorktreeManager:
    return WorktreeManager(repo_root=Path(row["repo_root"]),
                           path=Path(row["path"]), branch=row["branch"])


@dataclass(frozen=True)
class ApplyOutcome:
    """Result of an apply attempt.

    ``detail`` carries the worktree's current status for "not_active", or
    the raw WorktreeError text for "failed" (server-side logging only).
    """
    kind: Literal["turn_busy", "not_active", "failed", "applied"]
    detail: str = ""
    stats: list | None = None


def apply_workspace(
    repo: AssistantStore, sid: str,
    *, claim_turn: ClaimTurn, release_turn: ReleaseTurn,
) -> ApplyOutcome:
    """Apply the worktree diff onto the user's repo and advance the row to
    "applied". Claims the turn slot first so a concurrent /messages turn (or
    another apply/pr) sees "turn_busy" instead of racing the same worktree."""
    if not claim_turn(sid):
        return ApplyOutcome("turn_busy")
    try:
        row = repo.get_worktree(sid)  # re-read under the claim
        if row is None or row["status"] != "active":
            return ApplyOutcome("not_active", detail=row["status"] if row else "gone")
        manager = _manager(row)
        try:
            stats = manager.apply_to_repo()
        except WorktreeError as exc:
            return ApplyOutcome("failed", detail=str(exc))
        repo.set_worktree_status(sid, "applied")
        try:
            manager.remove()
        except WorktreeError:
            _logger.warning("worktree remove failed after apply for %s", sid)
        return ApplyOutcome("applied", stats=stats)
    finally:
        release_turn(sid)


@dataclass(frozen=True)
class PrOutcome:
    """Result of a PR-creation attempt.

    ``detail`` carries the worktree's current status for "not_active", or
    the raw WorktreeError text for "failed" (server-side logging only).
    ``result`` is ``WorktreeManager.create_pr``'s fail-soft body on success
    (a missing/None ``prUrl`` there means push or ``gh`` failed, not that
    this call raised).
    """
    kind: Literal["turn_busy", "not_active", "failed", "created"]
    detail: str = ""
    result: dict | None = None


def create_workspace_pr(
    repo: AssistantStore, sid: str, title: str, body: str,
    *, claim_turn: ClaimTurn, release_turn: ReleaseTurn,
) -> PrOutcome:
    """Commit, push, and open a PR from the worktree; advance the row to
    "pr_created" only once a PR URL actually comes back (fail-soft cases
    leave the row "active" so the user can retry)."""
    if not claim_turn(sid):
        return PrOutcome("turn_busy")
    try:
        row = repo.get_worktree(sid)  # re-read under the claim
        if row is None or row["status"] != "active":
            return PrOutcome("not_active", detail=row["status"] if row else "gone")
        manager = _manager(row)
        try:
            result = manager.create_pr(title, body)
        except WorktreeError as exc:
            return PrOutcome("failed", detail=str(exc))
        if result.get("prUrl"):
            repo.set_worktree_status(sid, "pr_created")
            try:
                manager.remove(delete_branch=False)  # branch lives on the remote PR
            except WorktreeError:
                _logger.warning("worktree remove failed after pr for %s", sid)
        return PrOutcome("created", result=result)
    finally:
        release_turn(sid)


@dataclass(frozen=True)
class DiscardOutcome:
    """Result of a discard attempt.

    ``detail`` carries the worktree's current status for "gone"/"not_active",
    or the raw WorktreeError text for "failed" (server-side logging only).
    """
    kind: Literal["turn_busy", "gone", "not_active", "failed", "discarded"]
    detail: str = ""


def discard_workspace(
    repo: AssistantStore, sid: str,
    *, claim_turn: ClaimTurn, release_turn: ReleaseTurn,
) -> DiscardOutcome:
    """Remove the worktree/branch and advance the row to "discarded". Claims
    the turn slot like apply/pr: without this, discard raced an in-flight
    apply (overwriting "applied" with "discarded" while the changes sat in
    the user's real tree) and pulled the worktree out from under a running
    write turn."""
    if not claim_turn(sid):
        return DiscardOutcome("turn_busy")
    try:
        row = repo.get_worktree(sid)  # re-read under the claim
        if row is None:
            return DiscardOutcome("gone")
        if row["status"] not in ("active", "stale"):
            return DiscardOutcome("not_active", detail=row["status"])
        try:
            _manager(row).remove()
        except WorktreeError as exc:
            return DiscardOutcome("failed", detail=str(exc))
        repo.set_worktree_status(sid, "discarded")
        return DiscardOutcome("discarded")
    finally:
        release_turn(sid)
