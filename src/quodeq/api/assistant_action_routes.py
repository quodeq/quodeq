"""Drafted-action lifecycle routes for the embedded assistant: apply, reject.

Split out of assistant_routes.py (Task 10).
"""
from __future__ import annotations

from flask import Flask, current_app, jsonify

from quodeq.api._assistant_helpers import build_action_context, get_repository
from quodeq.api.helpers import error_response
from quodeq.assistant.apply_action import apply_drafted_action, reject_drafted_action


def register_assistant_action_routes(app: Flask) -> None:
    @app.post("/api/assistant/actions/<action_id>/apply")
    def apply_assistant_action(action_id: str):
        repo = get_repository(app)
        outcome = apply_drafted_action(repo, action_id, build_action_context(current_app))
        if outcome.kind == "unknown_action":
            body, status = error_response("unknown action", 404, "UNKNOWN_ACTION")
            return jsonify(body), status
        if outcome.kind == "read_only":
            body, status = error_response("read-only session", 403, "READ_ONLY_SESSION")
            return jsonify(body), status
        if outcome.kind == "already":
            body, status = error_response(
                f"action already {outcome.detail}", 409, "ACTION_ALREADY_RESOLVED")
            return jsonify(body), status
        if outcome.kind == "unsupported":
            body, status = error_response(
                "unsupported action type", 400, "UNSUPPORTED_ACTION_TYPE")
            return jsonify(body), status
        if outcome.kind == "invalid":
            body, status = error_response(outcome.detail, 400, "INVALID_ACTION")
            return jsonify(body), status
        if outcome.kind == "conflict":
            body, status = error_response(outcome.detail, 409, "ACTION_CONFLICT")
            return jsonify(body), status
        return jsonify({"applied": True, "result": outcome.result}), 200

    @app.post("/api/assistant/actions/<action_id>/reject")
    def reject_assistant_action(action_id: str):
        repo = get_repository(app)
        outcome = reject_drafted_action(repo, action_id)
        if outcome.kind == "unknown_action":
            body, status = error_response("unknown action", 404, "UNKNOWN_ACTION")
            return jsonify(body), status
        if outcome.kind == "read_only":
            body, status = error_response("read-only session", 403, "READ_ONLY_SESSION")
            return jsonify(body), status
        if outcome.kind == "already":
            body, status = error_response(
                f"action already {outcome.detail}", 409, "ACTION_ALREADY_RESOLVED")
            return jsonify(body), status
        return jsonify({"status": "rejected"}), 200
