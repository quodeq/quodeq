"""Workspace (fix-worktree) HTTP surface: status, diff, apply / pr / discard.

Integration is HUMAN-ONLY: these routes are called by UI buttons behind the
app-wide auth + CSRF stack; they are never exposed as model tools. The
worktree/branch always comes from the session's stored row, never the client."""
from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, jsonify, request

from quodeq.api._assistant_helpers import get_repository
from quodeq.assistant.worktree import (
    WorktreeError, WorktreeManager, diff_stats, diff_text, gc_stale_worktrees)

_logger = logging.getLogger(__name__)


def _manager(row: dict) -> WorktreeManager:
    return WorktreeManager(repo_root=Path(row["repo_root"]),
                           path=Path(row["path"]), branch=row["branch"])


def register_assistant_workspace_routes(app: Flask) -> None:
    def _lookup(sid: str):
        """(repo, row, error_response); runs the one-shot stale GC first."""
        repo = get_repository(app)
        if repo.get_session(sid) is None:
            return None, None, (jsonify({"error": "unknown session"}), 404)
        if not getattr(app, "_worktree_gc_done", False):
            gc_stale_worktrees(repo)
            app._worktree_gc_done = True
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
            return jsonify({"error": str(exc)}), 500

    @app.post("/api/assistant/sessions/<sid>/workspace/apply")
    def assistant_workspace_apply(sid: str):
        repo, row, err = _lookup(sid)
        if err:
            return err
        if row is None:
            return jsonify({"error": "no worktree"}), 404
        from quodeq.api.assistant_routes import _release_turn, _try_claim_turn
        if not _try_claim_turn(sid):
            return jsonify({"error": "a turn or workspace action is in progress;"
                            " wait for it to finish"}), 409
        try:
            row = repo.get_worktree(sid)  # re-read under the claim
            if row is None or row["status"] != "active":
                return jsonify({"error": "worktree already "
                                f"{row['status'] if row else 'gone'}"}), 409
            manager = _manager(row)
            try:
                stats = manager.apply_to_repo()
            except WorktreeError as exc:
                return jsonify({"error": str(exc)}), 409
            repo.set_worktree_status(sid, "applied")
            try:
                manager.remove()
            except WorktreeError:
                _logger.warning("worktree remove failed after apply for %s", sid)
            return jsonify({"applied": True, "stats": stats})
        finally:
            _release_turn(sid)

    @app.post("/api/assistant/sessions/<sid>/workspace/pr")
    def assistant_workspace_pr(sid: str):
        repo, row, err = _lookup(sid)
        if err:
            return err
        if row is None:
            return jsonify({"error": "no worktree"}), 404
        from quodeq.api.assistant_routes import _release_turn, _try_claim_turn
        if not _try_claim_turn(sid):
            return jsonify({"error": "a turn or workspace action is in progress;"
                            " wait for it to finish"}), 409
        try:
            row = repo.get_worktree(sid)  # re-read under the claim
            if row is None or row["status"] != "active":
                return jsonify({"error": "worktree already "
                                f"{row['status'] if row else 'gone'}"}), 409
            body = request.get_json(silent=True) or {}
            manager = _manager(row)
            try:
                result = manager.create_pr(str(body.get("title", "")),
                                           str(body.get("body", "")))
            except WorktreeError as exc:
                return jsonify({"error": str(exc)}), 500
            if result.get("prUrl"):
                repo.set_worktree_status(sid, "pr_created")
                try:
                    manager.remove(delete_branch=False)  # branch lives on the remote PR
                except WorktreeError:
                    _logger.warning("worktree remove failed after pr for %s", sid)
            return jsonify(result)
        finally:
            _release_turn(sid)

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
        if not _try_claim_turn(sid):
            return jsonify({"error": "a turn or workspace action is in progress;"
                            " wait for it to finish"}), 409
        try:
            row = repo.get_worktree(sid)  # re-read under the claim
            if row is None:
                return jsonify({"error": "no worktree"}), 404
            if row["status"] not in ("active", "stale"):
                return jsonify({"error": f"worktree already {row['status']}"}), 409
            try:
                _manager(row).remove()
            except WorktreeError as exc:
                return jsonify({"error": str(exc)}), 500
            repo.set_worktree_status(sid, "discarded")
            return jsonify({"discarded": True})
        finally:
            _release_turn(sid)
