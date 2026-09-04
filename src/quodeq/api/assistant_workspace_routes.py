"""Workspace (fix-worktree) HTTP surface: status, diff, apply / pr / discard.

Integration is HUMAN-ONLY: these routes are called by UI buttons behind the
app-wide auth + CSRF stack; they are never exposed as model tools. The
worktree/branch always comes from the session's stored row, never the client."""
from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, jsonify, request

from quodeq.api._assistant_helpers import get_repository, run_assistant_hygiene
from quodeq.api.helpers import error_response
from quodeq.assistant.workspace_actions import (
    apply_workspace, create_workspace_pr, discard_workspace)
from quodeq.assistant.worktree import WorktreeError, diff_stats, diff_text

_logger = logging.getLogger(__name__)


def register_assistant_workspace_routes(app: Flask) -> None:
    def _lookup(sid: str):
        """(repo, row, error_response); runs one-shot worktree/db hygiene first."""
        repo = get_repository(app)
        if repo.get_session(sid) is None:
            return None, None, (jsonify({"error": "unknown session"}), 404)
        run_assistant_hygiene(app)
        return repo, repo.get_worktree(sid), None

    @app.get("/api/assistant/sessions/<sid>/workspace")
    def assistant_workspace_status(sid: str):
        repo, row, err = _lookup(sid)
        if err:
            return err
        session = repo.get_session(sid)
        pending = [{"sessionId": r["session_id"], "branch": r["branch"]}
                   for r in repo.list_worktrees("active",
                                                project_id=session.get("project_id"))
                   if r["session_id"] != sid]
        worktree = None
        if row is not None:
            active = row["status"] == "active" and Path(row["path"]).is_dir()
            stats = []
            if active:
                try:
                    stats = diff_stats(Path(row["path"]))
                except WorktreeError:
                    stats = []
            worktree = {"branch": row["branch"], "status": row["status"],
                        "filesChanged": len(stats), "stats": stats,
                        "createdAt": row["created_at"]}
        return jsonify({"worktree": worktree, "pending": pending})

    @app.get("/api/assistant/sessions/<sid>/workspace/diff")
    def assistant_workspace_diff(sid: str):
        repo, row, err = _lookup(sid)
        if err:
            return err
        if row is None or row["status"] != "active":
            return jsonify({"error": "no active worktree"}), 404
        try:
            text = diff_text(Path(row["path"]))
            truncated = len(text) > 2_000_000  # a diff this size is pathological
            return jsonify({"diff": text[:2_000_000], "truncated": truncated,
                            "stats": diff_stats(Path(row["path"]))})
        except WorktreeError as exc:
            _logger.warning("workspace diff failed for %s: %s", sid, exc)
            body, status = error_response(
                "failed to compute the workspace diff", 500, "WORKSPACE_DIFF_FAILED")
            return jsonify(body), status

    @app.post("/api/assistant/sessions/<sid>/workspace/apply")
    def assistant_workspace_apply(sid: str):
        repo, row, err = _lookup(sid)
        if err:
            return err
        if row is None:
            return jsonify({"error": "no worktree"}), 404
        from quodeq.api.assistant_routes import _release_turn, _try_claim_turn
        outcome = apply_workspace(repo, sid, claim_turn=_try_claim_turn,
                                  release_turn=_release_turn)
        if outcome.kind == "turn_busy":
            body, status = error_response(
                "a turn or workspace action is in progress; wait for it to finish",
                409, "TURN_IN_PROGRESS")
            return jsonify(body), status
        if outcome.kind == "not_active":
            return jsonify({"error": f"worktree already {outcome.detail}"}), 409
        if outcome.kind == "failed":
            _logger.warning("workspace apply failed for %s: %s", sid, outcome.detail)
            body, status = error_response(
                "failed to apply the workspace changes", 409, "WORKSPACE_APPLY_FAILED")
            return jsonify(body), status
        return jsonify({"applied": True, "stats": outcome.stats})

    @app.post("/api/assistant/sessions/<sid>/workspace/pr")
    def assistant_workspace_pr(sid: str):
        repo, row, err = _lookup(sid)
        if err:
            return err
        if row is None:
            return jsonify({"error": "no worktree"}), 404
        from quodeq.api.assistant_routes import _release_turn, _try_claim_turn
        req_body = request.get_json(silent=True) or {}
        outcome = create_workspace_pr(
            repo, sid, str(req_body.get("title", "")), str(req_body.get("body", "")),
            claim_turn=_try_claim_turn, release_turn=_release_turn)
        if outcome.kind == "turn_busy":
            return jsonify({"error": "a turn or workspace action is in progress;"
                            " wait for it to finish"}), 409
        if outcome.kind == "not_active":
            return jsonify({"error": f"worktree already {outcome.detail}"}), 409
        if outcome.kind == "failed":
            _logger.warning("workspace pr creation failed for %s: %s", sid, outcome.detail)
            resp_body, status = error_response(
                "failed to create the pull request", 500, "WORKSPACE_PR_FAILED")
            return jsonify(resp_body), status
        return jsonify(outcome.result)

    @app.post("/api/assistant/sessions/<sid>/workspace/discard")
    def assistant_workspace_discard(sid: str):
        repo, row, err = _lookup(sid)
        if err:
            return err
        if row is None:
            return jsonify({"error": "no worktree"}), 404
        from quodeq.api.assistant_routes import _release_turn, _try_claim_turn
        # Claim the turn slot like apply/pr: without this, discard raced an
        # in-flight apply (overwriting "applied" with "discarded" while the
        # changes sat in the user's real tree) and pulled the worktree out
        # from under a running write turn.
        outcome = discard_workspace(repo, sid, claim_turn=_try_claim_turn,
                                    release_turn=_release_turn)
        if outcome.kind == "turn_busy":
            return jsonify({"error": "a turn or workspace action is in progress;"
                            " wait for it to finish"}), 409
        if outcome.kind == "gone":
            return jsonify({"error": "no worktree"}), 404
        if outcome.kind == "not_active":
            return jsonify({"error": f"worktree already {outcome.detail}"}), 409
        if outcome.kind == "failed":
            _logger.warning("workspace discard failed for %s: %s", sid, outcome.detail)
            body, status = error_response(
                "failed to discard the workspace", 500, "WORKSPACE_DISCARD_FAILED")
            return jsonify(body), status
        return jsonify({"discarded": True})
