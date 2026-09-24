"""Each assistant use-case module has one outcome-kind vocabulary: the
workspace apply/pr/discard flows share OutcomeKind, the drafted-action
apply/reject flows share ActionOutcomeKind. The routes branch on members."""
from __future__ import annotations

from quodeq.assistant.apply_action import ActionOutcomeKind, ApplyOutcome, RejectOutcome
from quodeq.assistant.workspace_actions import DiscardOutcome, OutcomeKind, PrOutcome


def test_workspace_outcome_kinds():
    assert {k.value for k in OutcomeKind} == {
        "turn_busy", "not_active", "gone", "failed", "applied", "created", "discarded",
    }
    assert DiscardOutcome(OutcomeKind.GONE).kind == "gone"
    assert PrOutcome(OutcomeKind.FAILED, detail="x").kind is OutcomeKind.FAILED


def test_action_outcome_kinds():
    assert {k.value for k in ActionOutcomeKind} == {
        "unknown_action", "read_only", "already", "unsupported", "invalid", "conflict", "applied", "rejected",
    }
    assert ApplyOutcome(ActionOutcomeKind.APPLIED).kind == "applied"
    assert RejectOutcome(ActionOutcomeKind.READ_ONLY).kind is ActionOutcomeKind.READ_ONLY
