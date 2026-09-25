"""Drafted-action lifecycle routes for the embedded assistant: apply, reject.

Split out of assistant_routes.py.
"""
from __future__ import annotations

from flask import Flask, current_app, jsonify

from quodeq.api._assistant_helpers import build_action_context, get_repository
from quodeq.api._constants import CODE_INVALID_ACTION
from quodeq.api.helpers import json_error
from quodeq.assistant.apply_action import (
    ActionOutcomeKind,
    ApplyOutcome,
    RejectOutcome,
    apply_drafted_action,
    reject_drafted_action,
)


def _resolution_error(outcome: ApplyOutcome | RejectOutcome):
    """The error response for the outcomes apply and reject answer alike, else None.

    Both routes reject an unknown action id (404), a read-only session (403)
    and an action someone already resolved (409) with the same text and code.
    """
    if outcome.kind == ActionOutcomeKind.UNKNOWN_ACTION:
        return json_error("unknown action", 404, "UNKNOWN_ACTION")
    if outcome.kind == ActionOutcomeKind.READ_ONLY:
        return json_error("read-only session", 403, "READ_ONLY_SESSION")
    if outcome.kind == ActionOutcomeKind.ALREADY:
        return json_error(f"action already {outcome.detail}", 409, "ACTION_ALREADY_RESOLVED")
    return None


def register_assistant_action_routes(app: Flask) -> None:
    """Bind the apply/reject routes for actions the assistant has drafted."""
    @app.post("/api/assistant/actions/<action_id>/apply")
    def apply_assistant_action(action_id: str):
        repo = get_repository(app)
        outcome = apply_drafted_action(repo, action_id, build_action_context(current_app))
        shared = _resolution_error(outcome)
        if shared is not None:
            return shared
        if outcome.kind == ActionOutcomeKind.UNSUPPORTED:
            return json_error("unsupported action type", 400, "UNSUPPORTED_ACTION_TYPE")
        if outcome.kind == ActionOutcomeKind.INVALID:
            return json_error(outcome.detail, 400, CODE_INVALID_ACTION)
        if outcome.kind == ActionOutcomeKind.CONFLICT:
            return json_error(outcome.detail, 409, "ACTION_CONFLICT")
        return jsonify({"applied": True, "result": outcome.result}), 200

    @app.post("/api/assistant/actions/<action_id>/reject")
    def reject_assistant_action(action_id: str):
        repo = get_repository(app)
        outcome = reject_drafted_action(repo, action_id)
        shared = _resolution_error(outcome)
        if shared is not None:
            return shared
        return jsonify({"status": "rejected"}), 200
