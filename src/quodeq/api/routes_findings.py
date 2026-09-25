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
from typing import Any, Callable

from flask import Flask, Response, jsonify, request

from quodeq.api._constants import CODE_INVALID_PARAM, CODE_MISSING_PARAM, CODE_NOT_FOUND, QUERY_FLAG_TRUE
from quodeq.api.helpers import json_error, optional_json_object_or_error, page_params
from quodeq.services.deleted import delete_all_dismissed, delete_finding
from quodeq.services.dismissed_listing import load_dismissed
from quodeq.services.dismissed import dismiss_finding, restore_finding, restore_all_findings
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
_MAX_FINDINGS_LIST_LIMIT = 5000


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


class _ProjectNotFoundError(Exception):
    """Raised by `_project_dir`; the errorhandler registered in
    `register_findings_routes` turns it into this file's own
    {"error", "code"} shape instead of Flask's default 404 body."""


def _project_dir(evaluations_dir: str, project: str) -> Path:
    """As above, but 404 when the project has no directory.

    For the mutating endpoints, which have nothing to act on without one.
    Read endpoints that answer "nothing here" with an empty list call
    _project_dir_or_none directly.
    """
    resolved = _project_dir_or_none(evaluations_dir, project)
    if resolved is None:
        raise _ProjectNotFoundError(project)
    return resolved


def _finding_target_or_error(
    body: dict[str, Any],
) -> tuple[dict[str, Any] | None, tuple[Response, int] | None]:
    """Parse and validate the project/req/file/line target shared by dismiss,
    restore, and unverify. Returns the target dict, or None plus the ready
    error response. ``fingerprint`` (restore names a dismissed entry by it)
    is optional and only type-checked here.
    """
    project = body.get("project", "")
    req = body.get("req", "")
    file = body.get("file", "")
    line = body.get("line")
    if not project or not req or not file or line is None:
        return None, (jsonify({"error": "project, req, file, and line are required", "code": CODE_MISSING_PARAM}), 400)
    type_err = _invalid_body_fields(body, ("project", "req", "file", "fingerprint"), ("line",))
    if type_err:
        return None, (jsonify({"error": type_err, "code": CODE_INVALID_PARAM}), 400)
    return {"project": project, "req": req, "file": file, "line": line}, None


def _eval_dir(app: Flask) -> str:
    return app.config.get("EVALUATIONS_DIR") or get_evaluations_dir()


def _run_id(body: dict) -> str | None:
    """The run id a findings request names, under either the snake or camel key."""
    return body.get("run_id") or body.get("runId")


def _scores_with_fallback(app: Flask, project: str, run_id: str | None) -> dict[str, Any] | None:
    return rescore_with_fallback(_eval_dir(app), project, run_id)


def _list_project_entries(
    app: Flask, lister: Callable[..., list],
) -> Response | tuple[dict[str, Any], int]:
    """Shared body of the dismissed/verified listings: clamp paging, resolve, list."""
    project = request.args.get("project", "")
    if not project:
        return jsonify([])
    # No limit param → return everything (capped at the hard maximum).
    # A malformed or out-of-range limit/offset answers 400; an explicit
    # limit above the hard maximum stays clamped (the UI asks for 5000).
    paging = page_params(request.args, default_limit=_MAX_FINDINGS_LIST_LIMIT)
    if isinstance(paging[0], dict):
        return paging
    limit, offset = paging
    limit = min(limit, _MAX_FINDINGS_LIST_LIMIT)
    project_dir = _project_dir_or_none(_eval_dir(app), project)
    if project_dir is None:
        return jsonify([])
    return jsonify(lister(project_dir, offset=offset, limit=limit))


def _mutate_finding(
    app: Flask,
    mutate: Callable[[Path, dict[str, Any], str | None], object],
    delta_for: Callable[..., Any],
) -> tuple[Response, int]:
    """Apply *mutate* to the finding named in the request body, then rescore."""
    body = optional_json_object_or_error(CODE_INVALID_PARAM)
    if not isinstance(body, dict):
        return jsonify(body[0]), body[1]
    target, err = _finding_target_or_error(body)
    if err is not None:
        return err
    run_id = _run_id(body)
    mutate(_project_dir(_eval_dir(app), target["project"]), body, run_id)
    scores = _scores_with_fallback(app, target["project"], run_id)
    delta = delta_for(
        _eval_dir(app), target["project"], run_id,
        {"req": target["req"], "file": target["file"], "line": target["line"]},
    )
    return jsonify({"scores": scores, "delta": delta}), 200


def _mutate_project(
    app: Flask,
    mutate: Callable[[Path], int],
    delta_for: Callable[..., Any],
    count_key: str,
) -> tuple[Response, int]:
    """Apply *mutate* to every entry of the request body's project, then rescore."""
    body = optional_json_object_or_error(CODE_INVALID_PARAM)
    if not isinstance(body, dict):
        return jsonify(body[0]), body[1]
    project = body.get("project", "")
    run_id = _run_id(body)
    if not project:
        return jsonify({"error": "project is required", "code": CODE_MISSING_PARAM}), 400
    count = mutate(_project_dir(_eval_dir(app), project))
    scores = _scores_with_fallback(app, project, run_id)
    delta = delta_for(_eval_dir(app), project, run_id)
    return jsonify({"ok": True, count_key: count, "scores": scores, "delta": delta}), 200


def _dismiss(app: Flask) -> tuple[Response, int]:
    return _mutate_finding(
        app, lambda project_dir, body, run_id: dismiss_finding(project_dir, body, run_id=run_id), dismiss_delta,
    )


def _restore(app: Flask) -> tuple[Response, int]:
    return _mutate_finding(
        app, lambda project_dir, body, _run_id: restore_finding(project_dir, body), restore_delta,
    )


def _restore_all(app: Flask) -> tuple[Response, int]:
    return _mutate_project(app, restore_all_findings, restore_all_delta, "restored")


def _delete(app: Flask) -> tuple[Response, int]:
    body = optional_json_object_or_error(CODE_INVALID_PARAM)
    if not isinstance(body, dict):
        return jsonify(body[0]), body[1]
    project = body.get("project", "")
    dimension = body.get("dimension", "")
    principle = body.get("principle", "")
    file = body.get("file", "")
    run_id = _run_id(body)
    if not project or not dimension or not principle or not file:
        return jsonify({"error": "project, dimension, principle, and file are required", "code": CODE_MISSING_PARAM}), 400
    type_err = _invalid_body_fields(body, ("project", "dimension", "principle", "file"))
    if type_err:
        return jsonify({"error": type_err, "code": CODE_INVALID_PARAM}), 400
    swept = delete_finding(_project_dir(_eval_dir(app), project), body)
    scores = _scores_with_fallback(app, project, run_id)
    delta = delete_delta(
        _eval_dir(app), project, run_id,
        {"dimension": dimension, "principle": principle, "file": file},
    )
    return jsonify({"ok": True, "swept": swept, "scores": scores, "delta": delta}), 200


def _delete_all(app: Flask) -> tuple[Response, int]:
    if request.args.get("confirm") != QUERY_FLAG_TRUE:
        return json_error(
            "Use ?confirm=true to confirm deletion", HTTPStatus.BAD_REQUEST, "CONFIRMATION_REQUIRED",
        )
    return _mutate_project(app, delete_all_dismissed, delete_all_delta, "deleted")


def _unverify(app: Flask) -> tuple[Response, int]:
    body = optional_json_object_or_error(CODE_INVALID_PARAM)
    if not isinstance(body, dict):
        return jsonify(body[0]), body[1]
    target, err = _finding_target_or_error(body)
    if err is not None:
        return err
    unverify_finding(_project_dir(_eval_dir(app), target["project"]), body)
    return jsonify({"ok": True}), 200


def register_findings_routes(app: Flask) -> None:
    """Register /api/findings/* routes."""

    @app.errorhandler(_ProjectNotFoundError)
    def _handle_project_not_found(_exc: _ProjectNotFoundError) -> tuple[Response, int]:
        # Same {"error", "code"} shape every other error branch in this
        # file returns, instead of Flask's default 404 HTML page that the
        # bare abort() _project_dir used to call would give.
        return json_error("Project not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)

    @app.get("/api/findings/dismissed")
    def list_dismissed() -> Response | tuple[dict[str, Any], int]:
        return _list_project_entries(app, load_dismissed)

    @app.post("/api/findings/dismiss")
    def dismiss() -> tuple[Response, int]:
        return _dismiss(app)

    @app.post("/api/findings/restore")
    def restore() -> tuple[Response, int]:
        return _restore(app)

    @app.post("/api/findings/restore-all")
    def restore_all() -> tuple[Response, int]:
        return _restore_all(app)

    @app.post("/api/findings/delete")
    def delete() -> tuple[Response, int]:
        return _delete(app)

    @app.post("/api/findings/delete-all")
    def delete_all() -> tuple[Response, int]:
        return _delete_all(app)

    @app.get("/api/findings/verified")
    def list_verified() -> Response | tuple[dict[str, Any], int]:
        return _list_project_entries(app, verified_entries)

    @app.post("/api/findings/unverify")
    def unverify() -> tuple[Response, int]:
        return _unverify(app)
