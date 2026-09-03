"""Unit tests for the apply_drafted_action use case (no Flask involved)."""

from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.assistant.apply_action import (
    ApplyOutcome, RejectOutcome, apply_drafted_action, reject_drafted_action,
)
from quodeq.assistant.tools._actions import ActionConflict, ActionContext, ActionSpec


def _ctx(tmp_path: Path) -> ActionContext:
    return ActionContext(
        evaluations_dir=tmp_path, evaluators_dir=tmp_path,
        compiled_dir=tmp_path, dimensions_file=tmp_path / "dimensions.json",
    )


def _spec(apply_fn) -> ActionSpec:
    return ActionSpec(
        action_type="fake", description="fake",
        validate=lambda payload, ctx: payload,
        summarize=lambda payload: {},
        apply=apply_fn,
    )


class FakeRepo:
    """In-memory AssistantStore slice used by the workflow."""

    def __init__(self, action: dict | None, session: dict | None = None):
        self.action = action
        self.session = session
        self.status_calls: list[tuple] = []

    def get_action(self, action_id: str) -> dict | None:
        return self.action

    def get_session(self, session_id: str) -> dict | None:
        return self.session

    def set_action_status(self, action_id: str, status: str, *, expected=None) -> bool:
        self.status_calls.append((action_id, status, expected))
        if expected is not None and self.action["status"] != expected:
            return False
        self.action["status"] = status
        return True


def _drafted(action_type: str = "fake") -> dict:
    return {"id": "a1", "session_id": "s1", "action_type": action_type,
            "payload": {"k": "v"}, "status": "drafted"}


class TestApplyDraftedAction:
    def test_unknown_action(self, tmp_path):
        repo = FakeRepo(action=None)
        outcome = apply_drafted_action(repo, "a1", _ctx(tmp_path), actions={})
        assert outcome == ApplyOutcome("unknown_action")

    def test_shared_session_is_read_only(self, tmp_path):
        repo = FakeRepo(action=_drafted(), session={"source": "shared"})
        outcome = apply_drafted_action(repo, "a1", _ctx(tmp_path), actions={})
        assert outcome.kind == "read_only"
        assert repo.status_calls == []

    def test_already_applied(self, tmp_path):
        action = _drafted()
        action["status"] = "applied"
        repo = FakeRepo(action=action)
        outcome = apply_drafted_action(repo, "a1", _ctx(tmp_path), actions={})
        assert outcome == ApplyOutcome("already", detail="applied")

    def test_unsupported_action_type(self, tmp_path):
        repo = FakeRepo(action=_drafted("nope"))
        outcome = apply_drafted_action(repo, "a1", _ctx(tmp_path), actions={})
        assert outcome.kind == "unsupported"
        assert repo.status_calls == []

    def test_applied_success_claims_before_side_effect(self, tmp_path):
        order: list[str] = []
        repo = FakeRepo(action=_drafted())

        def apply_fn(payload, ctx):
            order.append("apply")
            assert repo.action["status"] == "applied"  # claim happened first
            return {"ok": True, "payload": payload}

        outcome = apply_drafted_action(
            repo, "a1", _ctx(tmp_path), actions={"fake": _spec(apply_fn)})
        assert outcome == ApplyOutcome("applied", result={"ok": True, "payload": {"k": "v"}})
        assert order == ["apply"]
        assert repo.status_calls == [("a1", "applied", "drafted")]

    def test_cas_loser_sees_non_drafted_state(self, tmp_path):
        action = _drafted()
        repo = FakeRepo(action=action)
        original_set = repo.set_action_status

        def racing_set(action_id, status, *, expected=None):
            # Simulate the other request winning the claim first.
            action["status"] = "applied"
            return original_set(action_id, status, expected=expected)

        repo.set_action_status = racing_set
        outcome = apply_drafted_action(
            repo, "a1", _ctx(tmp_path),
            actions={"fake": _spec(lambda p, c: pytest.fail("must not run"))})
        assert outcome == ApplyOutcome("already", detail="applied")

    def test_value_error_releases_back_to_drafted(self, tmp_path):
        repo = FakeRepo(action=_drafted())

        def apply_fn(payload, ctx):
            raise ValueError("bad payload")

        outcome = apply_drafted_action(
            repo, "a1", _ctx(tmp_path), actions={"fake": _spec(apply_fn)})
        assert outcome == ApplyOutcome("invalid", detail="bad payload")
        assert repo.action["status"] == "drafted"
        assert repo.status_calls == [("a1", "applied", "drafted"), ("a1", "drafted", None)]

    def test_action_conflict_releases_back_to_drafted(self, tmp_path):
        repo = FakeRepo(action=_drafted())

        def apply_fn(payload, ctx):
            raise ActionConflict("already dismissed")

        outcome = apply_drafted_action(
            repo, "a1", _ctx(tmp_path), actions={"fake": _spec(apply_fn)})
        assert outcome == ApplyOutcome("conflict", detail="already dismissed")
        assert repo.action["status"] == "drafted"


def test_reject_drafted_action_success():
    repo = FakeRepo(action={"session_id": "s1", "status": "drafted"})
    outcome = reject_drafted_action(repo, "a1")
    assert outcome == RejectOutcome("rejected")
    assert repo.action["status"] == "rejected"


def test_reject_drafted_action_unknown():
    repo = FakeRepo(action=None)
    outcome = reject_drafted_action(repo, "a1")
    assert outcome.kind == "unknown_action"


def test_reject_drafted_action_read_only():
    repo = FakeRepo(
        action={"session_id": "s1", "status": "drafted"},
        session={"source": "shared"},
    )
    outcome = reject_drafted_action(repo, "a1")
    assert outcome.kind == "read_only"
    assert repo.action["status"] == "drafted"


def test_reject_drafted_action_conflict_when_already_applied():
    repo = FakeRepo(action={"session_id": "s1", "status": "applied"})
    outcome = reject_drafted_action(repo, "a1")
    assert outcome == RejectOutcome("already", detail="applied")
