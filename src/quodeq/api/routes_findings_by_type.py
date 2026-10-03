"""POST /api/findings/dismiss-by-type: close every active finding of one requirement in a scope."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify

from quodeq.api._constants import CODE_INVALID_PARAM, CODE_MISSING_PARAM, CODE_NOT_FOUND
from quodeq.api.helpers import json_error, optional_json_object_or_response
from quodeq.services.dismiss_by_type import DismissScope, dismiss_by_type
from quodeq.services.mutation_rescore import dismiss_many_delta, rescore_with_fallback
from quodeq.shared.utils import get_evaluations_dir
from quodeq.shared.validation import resolve_child_dir, validate_path_segment

_ROUTE = "/api/findings/dismiss-by-type"
_REQUIRED = ("project", "req", "dimension", "run_id")
_OPTIONAL = ("principle", "file", "reason")


def _validate(body: dict) -> tuple[Response, int] | None:
    if any(not body.get(key) for key in _REQUIRED):
        return json_error("project, req, dimension and run_id are required", HTTPStatus.BAD_REQUEST, CODE_MISSING_PARAM)
    fields = (*_REQUIRED, *_OPTIONAL)
    if any(body.get(key) is not None and not isinstance(body.get(key), str) for key in fields):
        return json_error("scope fields must be strings", HTTPStatus.BAD_REQUEST, CODE_INVALID_PARAM)
    return None


def _dirs(evaluations_dir: str, project: str, run_id: str) -> tuple[Path, Path] | None:
    """The project and run directories, or None when either does not exist."""
    try:
        validate_path_segment(project)
        validate_path_segment(run_id)
    except ValueError:
        return None
    project_dir = resolve_child_dir(evaluations_dir, project)
    run_dir = resolve_child_dir(project_dir, run_id) if project_dir else None
    return (Path(project_dir), Path(run_dir)) if run_dir else None


def _scope_of(body: dict) -> DismissScope:
    return DismissScope(
        req=body["req"], dimension=body["dimension"], principle=body.get("principle"),
        file=body.get("file"), reason=body.get("reason"),
    )


def register_findings_by_type_routes(app: Flask) -> None:
    """Bind the dismiss-by-type route."""

    def _eval_dir() -> str:
        return app.config.get("EVALUATIONS_DIR") or get_evaluations_dir()

    @app.post(_ROUTE)
    def dismiss_by_type_route() -> Response | tuple[Response, int]:
        """Dismiss every active finding of ``req`` in ``dimension`` (narrowed
        by ``principle`` / ``file``) for ``run_id``, then rescore."""
        body = optional_json_object_or_response(CODE_INVALID_PARAM)
        if not isinstance(body, dict):
            return body
        err = _validate(body)
        if err:
            return err
        evaluations_dir = _eval_dir()
        dirs = _dirs(evaluations_dir, body["project"], body["run_id"])
        if dirs is None:
            return json_error("Run not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
        project_dir, run_dir = dirs
        count = dismiss_by_type(project_dir, run_dir, _scope_of(body))
        scores = rescore_with_fallback(evaluations_dir, body["project"], body["run_id"])
        delta = dismiss_many_delta(evaluations_dir, body["project"], body["run_id"],
                                   req=body["req"], dimension=body["dimension"], count=count)
        return jsonify({"ok": True, "dismissed": count, "scores": scores, "delta": delta})
