"""Drafted-action lifecycle routes for the embedded assistant: apply, reject.

Split out of assistant_routes.py (Task 10).
"""
from __future__ import annotations

from flask import Flask, current_app, jsonify

from quodeq.api._assistant_helpers import build_action_context, get_repository
from quodeq.assistant.apply_action import apply_drafted_action


def register_assistant_action_routes(app: Flask) -> None:
    @app.post("/api/assistant/actions/<action_id>/apply")
    def apply_assistant_action(action_id: str):
        repo = get_repository(app)
        outcome = apply_drafted_action(repo, action_id, build_action_context(current_app))
        if outcome.kind == "unknown_action":
            return jsonify({"error": "unknown action"}), 404
        if outcome.kind == "read_only":
            return jsonify({"error": "read-only session"}), 403
        if outcome.kind == "already":
            return jsonify({"error": f"action already {outcome.detail}"}), 409
        if outcome.kind == "unsupported":
            return jsonify({"error": "unsupported action type"}), 400
        if outcome.kind == "invalid":
            return jsonify({"error": outcome.detail}), 400
        if outcome.kind == "conflict":
            return jsonify({"error": outcome.detail}), 409
        return jsonify({"applied": True, "result": outcome.result}), 200

    @app.post("/api/assistant/actions/<action_id>/reject")
    def reject_assistant_action(action_id: str):
        repo = get_repository(app)
        action = repo.get_action(action_id)
        if action is None:
            return jsonify({"error": "unknown action"}), 404
        owner = repo.get_session(action["session_id"])
        if owner is not None and (owner.get("source") or "local") == "shared":
            # Defense in depth: read-only sessions never draft actions
            # (draft_action is not registered), so nothing legitimate reaches
            # here. Refuse rather than mutate the local store under a shared
            # project id.
            return jsonify({"error": "read-only session"}), 403
        # Same replay guard as apply, made atomic: an applied action must
        # not flip to rejected on a stale card click, SSE replay, or a race
        # with a concurrent apply. The compare-and-set wins at most once.
        if not repo.set_action_status(action_id, "rejected", expected="drafted"):
            fresh = repo.get_action(action_id)
            state = fresh["status"] if fresh else "gone"
            return jsonify({"error": f"action already {state}"}), 409
        return jsonify({"status": "rejected"}), 200
