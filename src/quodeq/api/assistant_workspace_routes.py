"""Workspace (fix-worktree) HTTP surface: status, diff, apply / pr / discard.

Integration is HUMAN-ONLY: these routes are called by UI buttons behind the
app-wide auth + CSRF stack; they are never exposed as model tools. The
worktree/branch always comes from the session's stored row, never the client."""
from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, jsonify, request

from quodeq.api._assistant_helpers import get_repository, run_assistant_hygiene
from quodeq.api._constants import CODE_NO_ACTIVE_WORKTREE, CODE_UNKNOWN_SESSION, MESSAGE_UNKNOWN_SESSION
from quodeq.api.assistant_routes import release_app_turn, claim_app_turn
from quodeq.api.helpers import json_error
from quodeq.assistant.workspace_actions import (
    OutcomeKind, PrDraft, apply_workspace, create_workspace_pr, discard_workspace)
from quodeq.assistant.worktree import WorktreeError, WorktreeStatus, diff_stats, diff_text

_logger = logging.getLogger(__name__)

_MAX_DIFF_CHARS = 2_000_000  # a diff this size is pathological; the UI never shows more


def _lookup(app: Flask, sid: str):
    """(repo, row, error_response); runs one-shot worktree/db hygiene first."""
    repo = get_repository(app)
    if repo.get_session(sid) is None:
        return None, None, json_error(MESSAGE_UNKNOWN_SESSION, 404, CODE_UNKNOWN_SESSION)
    run_assistant_hygiene(app)
    return repo, repo.get_worktree(sid), None


def _worktree_summary(row) -> dict | None:
    if row is None:
        return None
    active = row["status"] == WorktreeStatus.ACTIVE and Path(row["path"]).is_dir()
    stats = []
    if active:
        try:
            stats = diff_stats(Path(row["path"]))
        except WorktreeError:
            stats = []
    return {"branch": row["branch"], "status": row["status"],
            "filesChanged": len(stats), "stats": stats,
            "createdAt": row["created_at"]}


def _workspace_status(app: Flask, sid: str):
    repo, row, err = _lookup(app, sid)
    if err:
        return err
    session = repo.get_session(sid)
    pending = [{"sessionId": r["session_id"], "branch": r["branch"]}
               for r in repo.list_worktrees(WorktreeStatus.ACTIVE,
                                            project_id=session.get("project_id"))
               if r["session_id"] != sid]
    return jsonify({"worktree": _worktree_summary(row), "pending": pending})


def _workspace_diff(app: Flask, sid: str):
    repo, row, err = _lookup(app, sid)
    if err:
        return err
    if row is None or row["status"] != WorktreeStatus.ACTIVE:
        return json_error("no active worktree", 404, CODE_NO_ACTIVE_WORKTREE)
    try:
        text = diff_text(Path(row["path"]))
        truncated = len(text) > _MAX_DIFF_CHARS
        return jsonify({"diff": text[:_MAX_DIFF_CHARS], "truncated": truncated,
                        "stats": diff_stats(Path(row["path"]))})
    except WorktreeError as exc:
        _logger.warning("workspace diff failed for %s: %s", sid, exc)
        return json_error("failed to compute the workspace diff", 500, "WORKSPACE_DIFF_FAILED")


def _workspace_target(app: Flask, sid: str):
    """``(repo, row, None)`` for a session that has a worktree row, else an error.

    Folds the lookup and the "no worktree" 404 that apply, pr and discard all
    answer with before they touch the worktree.
    """
    repo, row, err = _lookup(app, sid)
    if err:
        return None, None, err
    if row is None:
        return None, None, json_error("no worktree", 404, CODE_NO_ACTIVE_WORKTREE)
    return repo, row, None


def _turn_conflict(outcome):
    """The 409 a busy turn or an already-resolved worktree answers with, else None.

    Shared by apply, pr and discard: same text, same status, same error code.
    """
    if outcome.kind == OutcomeKind.TURN_BUSY:
        return json_error(
            "a turn or workspace action is in progress; wait for it to finish",
            409, "TURN_IN_PROGRESS")
    if outcome.kind == OutcomeKind.NOT_ACTIVE:
        return json_error(f"worktree already {outcome.detail}", 409, "WORKTREE_CONFLICT")
    return None


def _workspace_apply(app: Flask, sid: str):
    repo, _row, err = _workspace_target(app, sid)
    if err:
        return err
    outcome = apply_workspace(repo, sid, claim_turn=claim_app_turn,
                              release_turn=release_app_turn)
    conflict = _turn_conflict(outcome)
    if conflict is not None:
        return conflict
    if outcome.kind == OutcomeKind.FAILED:
        _logger.warning("workspace apply failed for %s: %s", sid, outcome.detail)
        return json_error("failed to apply the workspace changes", 409, "WORKSPACE_APPLY_FAILED")
    return jsonify({"applied": True, "stats": outcome.stats})


def _workspace_pr(app: Flask, sid: str):
    repo, _row, err = _workspace_target(app, sid)
    if err:
        return err
    req_body = request.get_json(silent=True) or {}
    draft = PrDraft(title=str(req_body.get("title", "")), body=str(req_body.get("body", "")))
    outcome = create_workspace_pr(
        repo, sid, draft, claim_turn=claim_app_turn, release_turn=release_app_turn)
    conflict = _turn_conflict(outcome)
    if conflict is not None:
        return conflict
    if outcome.kind == OutcomeKind.FAILED:
        _logger.warning("workspace pr creation failed for %s: %s", sid, outcome.detail)
        return json_error("failed to create the pull request", 500, "WORKSPACE_PR_FAILED")
    return jsonify(outcome.result)


def _workspace_discard(app: Flask, sid: str):
    repo, _row, err = _workspace_target(app, sid)
    if err:
        return err
    # Claim the turn slot like apply/pr: without this, discard raced an
    # in-flight apply (overwriting "applied" with "discarded" while the
    # changes sat in the user's real tree) and pulled the worktree out
    # from under a running write turn.
    outcome = discard_workspace(repo, sid, claim_turn=claim_app_turn,
                                release_turn=release_app_turn)
    conflict = _turn_conflict(outcome)
    if conflict is not None:
        return conflict
    if outcome.kind == OutcomeKind.GONE:
        return json_error("no worktree", 404, CODE_NO_ACTIVE_WORKTREE)
    if outcome.kind == OutcomeKind.FAILED:
        _logger.warning("workspace discard failed for %s: %s", sid, outcome.detail)
        return json_error("failed to discard the workspace", 500, "WORKSPACE_DISCARD_FAILED")
    return jsonify({"discarded": True})


def register_assistant_workspace_routes(app: Flask) -> None:
    """Bind the routes over an assistant session's worktree: status, diff, apply, PR, discard."""
    @app.get("/api/assistant/sessions/<sid>/workspace")
    def assistant_workspace_status(sid: str):
        return _workspace_status(app, sid)

    @app.get("/api/assistant/sessions/<sid>/workspace/diff")
    def assistant_workspace_diff(sid: str):
        return _workspace_diff(app, sid)

    @app.post("/api/assistant/sessions/<sid>/workspace/apply")
    def assistant_workspace_apply(sid: str):
        return _workspace_apply(app, sid)

    @app.post("/api/assistant/sessions/<sid>/workspace/pr")
    def assistant_workspace_pr(sid: str):
        return _workspace_pr(app, sid)

    @app.post("/api/assistant/sessions/<sid>/workspace/discard")
    def assistant_workspace_discard(sid: str):
        return _workspace_discard(app, sid)
