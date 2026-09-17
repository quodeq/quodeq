"""Drafted-action lifecycle routes for the embedded assistant: apply, reject.

Split out of assistant_routes.py (Task 10).
"""
from __future__ import annotations

from flask import Flask, current_app, jsonify

from quodeq.api._assistant_helpers import build_action_context, get_repository
from quodeq.api.helpers import json_error
from quodeq.assistant.apply_action import apply_drafted_action, reject_drafted_action


def register_assistant_action_routes(app: Flask) -> None:
    @app.post("/api/assistant/actions/<action_id>/apply")
    def apply_assistant_action(action_id: str):
        repo = get_repository(app)
        outcome = apply_drafted_action(repo, action_id, build_action_context(current_app))
        if outcome.kind == "unknown_action":
            return json_error("unknown action", 404, "UNKNOWN_ACTION")
        if outcome.kind == "read_only":
            return json_error("read-only session", 403, "READ_ONLY_SESSION")
        if outcome.kind == "already":
            return json_error(f"action already {outcome.detail}", 409, "ACTION_ALREADY_RESOLVED")
        if outcome.kind == "unsupported":
            return json_error("unsupported action type", 400, "UNSUPPORTED_ACTION_TYPE")
        if outcome.kind == "invalid":
            return json_error(outcome.detail, 400, "INVALID_ACTION")
        if outcome.kind == "conflict":
            return json_error(outcome.detail, 409, "ACTION_CONFLICT")
        return jsonify({"applied": True, "result": outcome.result}), 200

    @app.post("/api/assistant/actions/<action_id>/reject")
    def reject_assistant_action(action_id: str):
        repo = get_repository(app)
        outcome = reject_drafted_action(repo, action_id)
        if outcome.kind == "unknown_action":
            return json_error("unknown action", 404, "UNKNOWN_ACTION")
        if outcome.kind == "read_only":
            return json_error("read-only session", 403, "READ_ONLY_SESSION")
        if outcome.kind == "already":
            return json_error(f"action already {outcome.detail}", 409, "ACTION_ALREADY_RESOLVED")
        return jsonify({"status": "rejected"}), 200
