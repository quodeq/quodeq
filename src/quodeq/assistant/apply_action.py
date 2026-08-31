"""Apply-drafted-action use case, extracted from the HTTP route.

The workflow (ownership check, atomic drafted->applied claim, release on
failure, spec dispatch) is framework-free; the route maps each outcome to
its frozen HTTP response body.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from quodeq.assistant.tools._actions import ACTIONS, ActionConflict, ActionContext, ActionSpec
from quodeq.data.ports.assistant import AssistantStore


@dataclass(frozen=True)
class ApplyOutcome:
    """Result of an apply attempt; ``detail`` carries a state name or error."""
    kind: Literal["unknown_action", "read_only", "already", "unsupported",
                  "invalid", "conflict", "applied"]
    detail: str = ""
    result: dict | None = None


def apply_drafted_action(
    repo: AssistantStore, action_id: str, context: ActionContext,
    *, actions: Mapping[str, ActionSpec] = ACTIONS,
) -> ApplyOutcome:
    """Apply a drafted action, claiming the transition atomically first."""
    action = repo.get_action(action_id)
    if action is None:
        return ApplyOutcome("unknown_action")
    owner = repo.get_session(action["session_id"])
    if owner is not None and (owner.get("source") or "local") == "shared":
        # Defense in depth: read-only sessions never draft actions
        # (draft_action is not registered), so nothing legitimate reaches
        # here. Refuse rather than mutate the local store under a shared
        # project id.
        return ApplyOutcome("read_only")
    if action["status"] != "drafted":
        return ApplyOutcome("already", detail=action["status"])
    spec = actions.get(action["action_type"])
    if spec is None:
        return ApplyOutcome("unsupported")
    # Atomically claim the drafted->applied transition BEFORE running the
    # side effect, so a double-click / two-tab race can't run spec.apply
    # twice (which double-ran the dismiss rescore). The loser sees a
    # non-drafted row and 409s. On failure we release back to drafted so
    # the user can retry.
    if not repo.set_action_status(action_id, "applied", expected="drafted"):
        fresh = repo.get_action(action_id)
        state = fresh["status"] if fresh else "gone"
        return ApplyOutcome("already", detail=state)
    try:
        result = spec.apply(action["payload"], context)
    except ValueError as exc:
        repo.set_action_status(action_id, "drafted")
        return ApplyOutcome("invalid", detail=str(exc))
    except ActionConflict as exc:
        repo.set_action_status(action_id, "drafted")
        return ApplyOutcome("conflict", detail=str(exc))
    return ApplyOutcome("applied", result=result)
