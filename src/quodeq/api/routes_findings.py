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
from http import HTTPStatus
from pathlib import Path
from typing import Any

from flask import Flask, Response, abort, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.services.deleted import delete_all_dismissed, delete_finding
from quodeq.services.dismissed import dismiss_finding, load_dismissed, restore_finding, restore_all_findings
from quodeq.services.mutation_rescore import (
    delete_all_delta,
    delete_delta,
    dismiss_delta,
    rescore_with_fallback,
    restore_all_delta,
    restore_delta,
)
from quodeq.services.verified import unverify_finding, verified_entries
from quodeq.shared.utils import get_evaluations_dir
from quodeq.shared.validation import resolve_child_dir, validate_path_segment

_logger = logging.getLogger(__name__)
_MAX_DISMISSED_LIMIT = 5000

def _invalid_body_fields(
    body: dict[str, Any],
    str_fields: tuple[str, ...],
    int_fields: tuple[str, ...] = (),
) -> str | None:
    """Return a message naming mistyped body fields, or None when types are fine.

    Missing fields stay the caller's MISSING_PARAM concern; this only rejects
    present values of the wrong type (str fields must be str, int fields must
    be a non-bool int) so list/dict/number payloads get a 400 at the API
    boundary instead of crashing in the persistence layer.
    """
    bad: list[str] = []
    for name in str_fields:
        value = body.get(name)
        if value is not None and not isinstance(value, str):
            bad.append(f"{name} (must be a string)")
    for name in int_fields:
        value = body.get(name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            bad.append(f"{name} (must be an integer)")
    if bad:
        return f"invalid fields: {', '.join(bad)}"
    return None


def _project_dir_or_none(evaluations_dir: str, project: str) -> Path | None:
    """Resolve *project* to its directory by listing, or None if there is none.

    *project* is matched against real entries under *evaluations_dir* and never
    concatenated onto it, so a traversal or absolute-path value matches nothing
    instead of having to be contained after the fact.

    None means absent, not invalid: validate_path_segment has already rejected
    syntactically bad names above.
    """
    validate_path_segment(project)
    resolved = resolve_child_dir(evaluations_dir, project)
    return Path(resolved) if resolved is not None else None


def _project_dir(evaluations_dir: str, project: str) -> Path:
    """As above, but 404 when the project has no directory.

    For the mutating endpoints, which have nothing to act on without one.
    Read endpoints that answer "nothing here" with an empty list call
    _project_dir_or_none directly.
    """
    resolved = _project_dir_or_none(evaluations_dir, project)
    if resolved is None:
        abort(404, description="Project not found")
    return resolved


def register_findings_routes(app: Flask) -> None:
    """Register /api/findings/* routes."""

    def _eval_dir() -> str:
        return app.config.get("EVALUATIONS_DIR") or get_evaluations_dir()

    def _scores_with_fallback(
        project: str, run_id: str | None,
    ) -> dict[str, Any] | None:
        return rescore_with_fallback(_eval_dir(), project, run_id)

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
        project_dir = _project_dir_or_none(_eval_dir(), project)
        if project_dir is None:
            return jsonify([])
        return jsonify(load_dismissed(project_dir, offset=offset, limit=limit))

    @app.post("/api/findings/dismiss")
    def dismiss() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        req = body.get("req", "")
        file = body.get("file", "")
        line = body.get("line")
        run_id = body.get("run_id") or body.get("runId")
        if not project or not req or not file or line is None:
            return jsonify({"error": "project, req, file, and line are required", "code": "MISSING_PARAM"}), 400
        type_err = _invalid_body_fields(body, ("project", "req", "file"), ("line",))
        if type_err:
            return jsonify({"error": type_err, "code": "INVALID_PARAM"}), 400
        dismiss_finding(_project_dir(_eval_dir(), project), body)
        scores = _scores_with_fallback(project, run_id)
        delta = dismiss_delta(
            _eval_dir(), project, run_id, {"req": req, "file": file, "line": line},
        )
        return jsonify({"scores": scores, "delta": delta}), 200

    @app.post("/api/findings/restore")
    def restore() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        req = body.get("req", "")
        file = body.get("file", "")
        line = body.get("line")
        run_id = body.get("run_id") or body.get("runId")
        if not project or not req or not file or line is None:
            return jsonify({"error": "project, req, file, and line are required", "code": "MISSING_PARAM"}), 400
        type_err = _invalid_body_fields(body, ("project", "req", "file"), ("line",))
        if type_err:
            return jsonify({"error": type_err, "code": "INVALID_PARAM"}), 400
        restore_finding(_project_dir(_eval_dir(), project), body)
        scores = _scores_with_fallback(project, run_id)
        delta = restore_delta(
            _eval_dir(), project, run_id, {"req": req, "file": file, "line": line},
        )
        return jsonify({"scores": scores, "delta": delta}), 200

    @app.post("/api/findings/restore-all")
    def restore_all() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        run_id = body.get("run_id") or body.get("runId")
        if not project:
            return jsonify({"error": "project is required", "code": "MISSING_PARAM"}), 400
        count = restore_all_findings(_project_dir(_eval_dir(), project))
        scores = _scores_with_fallback(project, run_id)
        delta = restore_all_delta(_eval_dir(), project, run_id)
        return jsonify({"ok": True, "restored": count, "scores": scores, "delta": delta}), 200

    @app.post("/api/findings/delete")
    def delete() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        dimension = body.get("dimension", "")
        principle = body.get("principle", "")
        file = body.get("file", "")
        run_id = body.get("run_id") or body.get("runId")
        if not project or not dimension or not principle or not file:
            return jsonify({"error": "project, dimension, principle, and file are required", "code": "MISSING_PARAM"}), 400
        type_err = _invalid_body_fields(body, ("project", "dimension", "principle", "file"))
        if type_err:
            return jsonify({"error": type_err, "code": "INVALID_PARAM"}), 400
        swept = delete_finding(_project_dir(_eval_dir(), project), body)
        scores = _scores_with_fallback(project, run_id)
        delta = delete_delta(
            _eval_dir(), project, run_id,
            {"dimension": dimension, "principle": principle, "file": file},
        )
        return jsonify({"ok": True, "swept": swept, "scores": scores, "delta": delta}), 200

    @app.post("/api/findings/delete-all")
    def delete_all() -> tuple[Response, int]:
        if request.args.get("confirm") != "true":
            err_body, status = error_response(
                "Use ?confirm=true to confirm deletion", HTTPStatus.BAD_REQUEST, "CONFIRMATION_REQUIRED",
            )
            return jsonify(err_body), status
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        run_id = body.get("run_id") or body.get("runId")
        if not project:
            return jsonify({"error": "project is required", "code": "MISSING_PARAM"}), 400
        count = delete_all_dismissed(_project_dir(_eval_dir(), project))
        scores = _scores_with_fallback(project, run_id)
        delta = delete_all_delta(_eval_dir(), project, run_id)
        return jsonify({"ok": True, "deleted": count, "scores": scores, "delta": delta}), 200

    @app.get("/api/findings/verified")
    def list_verified() -> Response:
        project = request.args.get("project", "")
        if not project:
            return jsonify([])
        # No limit param → return everything (capped at the hard maximum).
        # An explicit limit is clamped to [1, _MAX_DISMISSED_LIMIT].
        raw_limit = request.args.get("limit", _MAX_DISMISSED_LIMIT, type=int)
        limit = max(1, min(raw_limit, _MAX_DISMISSED_LIMIT))
        offset = max(0, request.args.get("offset", 0, type=int))
        project_dir = _project_dir_or_none(_eval_dir(), project)
        if project_dir is None:
            return jsonify([])
        return jsonify(verified_entries(project_dir, offset=offset, limit=limit))

    @app.post("/api/findings/unverify")
    def unverify() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        req = body.get("req", "")
        file = body.get("file", "")
        line = body.get("line")
        if not project or not req or not file or line is None:
            return jsonify({"error": "project, req, file, and line are required", "code": "MISSING_PARAM"}), 400
        type_err = _invalid_body_fields(body, ("project", "req", "file"), ("line",))
        if type_err:
            return jsonify({"error": type_err, "code": "INVALID_PARAM"}), 400
        unverify_finding(_project_dir(_eval_dir(), project), body)
        return jsonify({"ok": True}), 200
