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
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from quodeq.assistant.worktree import WorktreeError, WorktreeManager
from quodeq.data.ports.assistant import AssistantStore

_logger = logging.getLogger(__name__)

ClaimTurn = Callable[[str], bool]
ReleaseTurn = Callable[[str], None]

# Outcome.kind's "failed" spelling -- a local closed vocabulary (see the
# Literal on each Outcome dataclass below), distinct from RunState/JobStatus
# even though it spells the same word; named so the ratchet in
# tools/check_vocab_literals.py doesn't mistake this for that vocabulary.
OUTCOME_FAILED = "failed"


def _manager(row: dict) -> WorktreeManager:
    return WorktreeManager(repo_root=Path(row["repo_root"]),
                           path=Path(row["path"]), branch=row["branch"])


_ACTIVE_ONLY = ("active",)


@dataclass(frozen=True, slots=True)
class _Claim:
    """The worktree row re-read under a claimed turn, or why there is none.

    ``refusal`` is "" when ``row`` is usable, else "turn_busy", "gone" or
    "not_active" (with the row's status in ``detail``).
    """

    row: dict | None = None
    refusal: str = ""
    detail: str = ""


@contextmanager
def _claimed_row(
    repo: AssistantStore, sid: str, claim_turn: ClaimTurn, release_turn: ReleaseTurn,
    allowed: tuple[str, ...],
) -> Iterator[_Claim]:
    """Claim the turn slot, re-read the row (state may have moved since the
    route's lookup) and gate it on *allowed*. Releases on every exit path
    once the claim succeeded."""
    if not claim_turn(sid):
        yield _Claim(refusal="turn_busy")
        return
    try:
        row = repo.get_worktree(sid)
        if row is None:
            yield _Claim(refusal="gone")
        elif row["status"] not in allowed:
            yield _Claim(refusal="not_active", detail=row["status"])
        else:
            yield _Claim(row=row)
    finally:
        release_turn(sid)


def _active_refusal(claim: _Claim) -> tuple[str, str]:
    """(kind, detail) for apply/pr, which report a missing row as not_active/"gone"."""
    if claim.refusal == "gone":
        return "not_active", "gone"
    return claim.refusal, claim.detail


def _remove_quietly(manager: WorktreeManager, sid: str, after: str, **kwargs) -> None:
    """Best-effort worktree removal once the row already moved on; logs only."""
    try:
        manager.remove(**kwargs)
    except WorktreeError:
        _logger.warning("worktree remove failed after %s for %s", after, sid)


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
    with _claimed_row(repo, sid, claim_turn, release_turn, _ACTIVE_ONLY) as claim:
        if claim.refusal:
            return ApplyOutcome(*_active_refusal(claim))
        manager = _manager(claim.row)
        try:
            stats = manager.apply_to_repo()
        except WorktreeError as exc:
            return ApplyOutcome(OUTCOME_FAILED, detail=str(exc))
        repo.set_worktree_status(sid, "applied")
        _remove_quietly(manager, sid, "apply")
        return ApplyOutcome("applied", stats=stats)


@dataclass(frozen=True, slots=True)
class PrDraft:
    """The pull request the user asked for: its title and body text."""

    title: str
    body: str


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
    repo: AssistantStore, sid: str, draft: PrDraft,
    *, claim_turn: ClaimTurn, release_turn: ReleaseTurn,
) -> PrOutcome:
    """Commit, push, and open a PR from the worktree; advance the row to
    "pr_created" only once a PR URL actually comes back (fail-soft cases
    leave the row "active" so the user can retry)."""
    with _claimed_row(repo, sid, claim_turn, release_turn, _ACTIVE_ONLY) as claim:
        if claim.refusal:
            return PrOutcome(*_active_refusal(claim))
        manager = _manager(claim.row)
        try:
            result = manager.create_pr(draft.title, draft.body)
        except WorktreeError as exc:
            return PrOutcome(OUTCOME_FAILED, detail=str(exc))
        if result.get("prUrl"):
            repo.set_worktree_status(sid, "pr_created")
            _remove_quietly(manager, sid, "pr", delete_branch=False)  # branch lives on the remote PR
        return PrOutcome("created", result=result)


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
    with _claimed_row(repo, sid, claim_turn, release_turn, ("active", "stale")) as claim:
        if claim.refusal:
            return DiscardOutcome(claim.refusal, detail=claim.detail)
        try:
            _manager(claim.row).remove()
        except WorktreeError as exc:
            return DiscardOutcome(OUTCOME_FAILED, detail=str(exc))
        repo.set_worktree_status(sid, "discarded")
        return DiscardOutcome("discarded")
