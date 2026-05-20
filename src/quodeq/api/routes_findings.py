"""API routes for dismissing and restoring individual findings.

Mutating endpoints (dismiss, restore, delete) accept an optional ``run_id``.
When present, the endpoint returns the rescored payload for that run in the
response body — same shape as ``GET /api/projects/<p>/scores/<run>``. This
lets the UI apply the new scores synchronously from the POST response,
instead of subscribing to an SSE stream and hoping ``scores.updated`` fires
in time. (For the history of why this design exists, see the diagnose
sessions that ended in PRs #525-#528.)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Flask, Response, abort, jsonify, request

from quodeq.services.deleted import delete_all_dismissed, delete_finding
from quodeq.services.dismissed import dismiss_finding, load_dismissed, restore_finding, restore_all_findings
from quodeq.shared.utils import get_evaluations_dir
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)
_MAX_DISMISSED_LIMIT = 5000


def _project_dir(evaluations_dir: str, project: str) -> Path:
    validate_path_segment(project)
    base = Path(evaluations_dir).resolve()
    resolved = (base / project).resolve()
    if not resolved.is_relative_to(base):
        abort(400, description="Invalid project path")
    return resolved


def _rescore_run(evaluations_dir: str, project: str, run_id: str | None) -> dict[str, Any] | None:
    """Compute the rescored payload for the run referenced in a mutation body.

    Returns ``None`` when ``run_id`` is missing or the run directory cannot
    be resolved. Callers fold the result into the response body so the UI
    can apply the new scores without a follow-up GET.
    """
    if not run_id:
        return None
    try:
        validate_path_segment(run_id)
    except ValueError:
        return None
    from quodeq.services.scoring import get_scores_raw  # noqa: PLC0415

    reports_root = Path(evaluations_dir).resolve()
    try:
        return get_scores_raw(reports_root, project, run_id)
    except FileNotFoundError:
        return None
    except Exception:
        # Never let a rescore failure break the mutation — the dismiss is
        # already persisted in actions.jsonl. Log and return None so the
        # client falls back to a refetch.
        _logger.warning("Rescore after mutation failed for %s/%s", project, run_id, exc_info=True)
        return None


def register_findings_routes(app: Flask) -> None:
    """Register /api/findings/* routes."""

    def _eval_dir() -> str:
        return app.config.get("EVALUATIONS_DIR") or get_evaluations_dir()

    @app.get("/api/findings/dismissed")
    def list_dismissed() -> Response:
        project = request.args.get("project", "")
        if not project:
            return jsonify([])
        # No limit param → return everything (capped at the hard maximum).
        # An explicit limit is clamped to [1, _MAX_DISMISSED_LIMIT].
        raw_limit = request.args.get("limit", _MAX_DISMISSED_LIMIT, type=int)
        limit = max(1, min(raw_limit, _MAX_DISMISSED_LIMIT))
        offset = max(0, request.args.get("offset", 0, type=int))
        items = load_dismissed(
            _project_dir(_eval_dir(), project),
            offset=offset,
            limit=limit,
        )
        return jsonify(items)

    @app.post("/api/findings/dismiss")
    def dismiss() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        req = body.get("req", "")
        file = body.get("file", "")
        line = body.get("line")
        run_id = body.get("run_id") or body.get("runId")
        if not project or not req or not file or line is None:
            return jsonify({"error": "project, req, file, and line are required"}), 400
        dismiss_finding(_project_dir(_eval_dir(), project), body)
        scores = _rescore_run(_eval_dir(), project, run_id)
        return jsonify({"scores": scores}), 200

    @app.post("/api/findings/restore")
    def restore() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        req = body.get("req", "")
        file = body.get("file", "")
        line = body.get("line")
        run_id = body.get("run_id") or body.get("runId")
        if not project or not req or not file or line is None:
            return jsonify({"error": "project, req, file, and line are required"}), 400
        restore_finding(_project_dir(_eval_dir(), project), body)
        scores = _rescore_run(_eval_dir(), project, run_id)
        return jsonify({"scores": scores}), 200

    @app.post("/api/findings/restore-all")
    def restore_all() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        run_id = body.get("run_id") or body.get("runId")
        if not project:
            return jsonify({"error": "project is required"}), 400
        count = restore_all_findings(_project_dir(_eval_dir(), project))
        scores = _rescore_run(_eval_dir(), project, run_id)
        return jsonify({"ok": True, "restored": count, "scores": scores}), 200

    @app.post("/api/findings/delete")
    def delete() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        dimension = body.get("dimension", "")
        principle = body.get("principle", "")
        file = body.get("file", "")
        run_id = body.get("run_id") or body.get("runId")
        if not project or not dimension or not principle or not file:
            return jsonify({"error": "project, dimension, principle, and file are required"}), 400
        swept = delete_finding(_project_dir(_eval_dir(), project), body)
        scores = _rescore_run(_eval_dir(), project, run_id)
        return jsonify({"ok": True, "swept": swept, "scores": scores}), 200

    @app.post("/api/findings/delete-all")
    def delete_all() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        run_id = body.get("run_id") or body.get("runId")
        if not project:
            return jsonify({"error": "project is required"}), 400
        count = delete_all_dismissed(_project_dir(_eval_dir(), project))
        scores = _rescore_run(_eval_dir(), project, run_id)
        return jsonify({"ok": True, "deleted": count, "scores": scores}), 200
