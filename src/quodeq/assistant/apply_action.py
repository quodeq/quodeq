"""Apply-drafted-action use case, extracted from the HTTP route.

The workflow (ownership check, atomic drafted->applied claim, release on
failure, spec dispatch) is framework-free; the route maps each outcome to
its frozen HTTP response body.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from quodeq.assistant.action_status import ActionStatus
from quodeq.assistant.tools.actions import ACTIONS, ActionConflict, ActionContext, ActionSpec
from quodeq.core.types.project_source import ProjectSource, session_source
from quodeq.data.ports.assistant import AssistantStore


class ActionOutcomeKind(StrEnum):
    """What an apply or reject of a drafted action concluded; the route maps each kind to its response."""

    UNKNOWN_ACTION = "unknown_action"
    READ_ONLY = "read_only"
    ALREADY = "already"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"
    CONFLICT = "conflict"
    APPLIED = "applied"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ApplyOutcome:
    """Result of an apply attempt; ``detail`` carries a state name or error."""
    kind: ActionOutcomeKind
    detail: str = ""
    result: dict | None = None


def _is_read_only_action(repo: AssistantStore, action: Mapping) -> bool:
    """True when *action* belongs to a shared, read-only session.

    Defense in depth: read-only sessions never draft actions (draft_action
    is not registered), so nothing legitimate reaches here. Both apply and
    reject refuse rather than mutate the local store under a shared project
    id.
    """
    owner = repo.get_session(action["session_id"])
    return owner is not None and session_source(owner) == ProjectSource.SHARED


def apply_drafted_action(
    repo: AssistantStore, action_id: str, context: ActionContext,
    *, actions: Mapping[str, ActionSpec] = ACTIONS,
) -> ApplyOutcome:
    """Apply a drafted action, claiming the transition atomically first."""
    action = repo.get_action(action_id)
    if action is None:
        return ApplyOutcome(ActionOutcomeKind.UNKNOWN_ACTION)
    if _is_read_only_action(repo, action):
        return ApplyOutcome(ActionOutcomeKind.READ_ONLY)
    if action["status"] != ActionStatus.DRAFTED:
        return ApplyOutcome(ActionOutcomeKind.ALREADY, detail=action["status"])
    spec = actions.get(action["action_type"])
    if spec is None:
        return ApplyOutcome(ActionOutcomeKind.UNSUPPORTED)
    # Atomically claim the drafted->applied transition BEFORE running the
    # side effect, so a double-click / two-tab race can't run spec.apply
    # twice (which double-ran the dismiss rescore). The loser sees a
    # non-drafted row and 409s. On failure we release back to drafted so
    # the user can retry.
    if not repo.set_action_status(action_id, ActionStatus.APPLIED, expected=ActionStatus.DRAFTED):
        fresh = repo.get_action(action_id)
        state = fresh["status"] if fresh else "gone"
        return ApplyOutcome(ActionOutcomeKind.ALREADY, detail=state)
    try:
        result = spec.apply(action["payload"], context)
    except ValueError as exc:
        repo.set_action_status(action_id, ActionStatus.DRAFTED)
        return ApplyOutcome(ActionOutcomeKind.INVALID, detail=str(exc))
    except ActionConflict as exc:
        repo.set_action_status(action_id, ActionStatus.DRAFTED)
        return ApplyOutcome(ActionOutcomeKind.CONFLICT, detail=str(exc))
    return ApplyOutcome(ActionOutcomeKind.APPLIED, result=result)


@dataclass(frozen=True)
class RejectOutcome:
    """Result of a reject attempt; ``detail`` carries a state name."""
    kind: ActionOutcomeKind
    detail: str = ""


def reject_drafted_action(repo: AssistantStore, action_id: str) -> RejectOutcome:
    """Reject a drafted action, claiming the transition atomically."""
    action = repo.get_action(action_id)
    if action is None:
        return RejectOutcome(ActionOutcomeKind.UNKNOWN_ACTION)
    if _is_read_only_action(repo, action):
        return RejectOutcome(ActionOutcomeKind.READ_ONLY)
    # Same replay guard as apply, made atomic: an applied action must not
    # flip to rejected on a stale card click, SSE replay, or a race with a
    # concurrent apply. The compare-and-set wins at most once.
    if not repo.set_action_status(action_id, ActionStatus.REJECTED, expected=ActionStatus.DRAFTED):
        fresh = repo.get_action(action_id)
        state = fresh["status"] if fresh else "gone"
        return RejectOutcome(ActionOutcomeKind.ALREADY, detail=state)
    return RejectOutcome(ActionOutcomeKind.REJECTED)
