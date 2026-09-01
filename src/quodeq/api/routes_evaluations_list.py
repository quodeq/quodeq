"""Evaluation listing, active-evaluation lookup, and creation routes."""
from __future__ import annotations

import logging
from http import HTTPStatus

from flask import Flask, Response, jsonify, request

from quodeq.api._evaluation_helpers import (
    _build_evaluation_options,
    _check_eval_rate_limit,
    _sanitize_url,
    _validate_ai_cmd,
    _validate_ai_cmd_path,
    _validate_ai_model,
)
from quodeq.api.helpers import error_response, scan_target_error, validate_evaluation_payload
from quodeq.shared.serialization import to_camel_dict
from quodeq.assistant import get_provider_configs
from quodeq.api.routes import _reports_dir
from quodeq.services.active_evaluation import find_active_evaluation
from quodeq.services.base import ActionProvider
from quodeq.shared.utils import is_repo_url

_logger = logging.getLogger(__name__)

# Cap on /api/evaluations ?limit= so a client cannot ask the server to materialize
# an unbounded list. limit=0 still means "no client cap" but we clamp the actual
# value the provider sees. 1000 is well above any realistic dashboard query.
_EVALUATIONS_LIST_HARD_CAP = 1000


def _validate_start_payload(payload: dict) -> Response | tuple[Response, int] | None:
    """Validate the POST /api/evaluations body. Returns an error response
    (or Flask's own error tuple) if invalid, else None."""
    validation_error = validate_evaluation_payload(payload)
    if validation_error:
        body, status = error_response(validation_error, HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
        return jsonify(body), status
    ai_cmd = payload.get("aiCmd") or None
    ai_cmd_error = _validate_ai_cmd(ai_cmd)
    if ai_cmd_error is not None:
        return ai_cmd_error
    ai_cmd_path_error = _validate_ai_cmd_path(ai_cmd, payload.get("aiCmdPath") or None)
    if ai_cmd_path_error is not None:
        return ai_cmd_path_error
    model_error = _validate_ai_model(
        ai_cmd, payload.get("aiModel") or None, get_provider_configs(),
    )
    if model_error is not None:
        return model_error
    return None


def register_evaluation_list_routes(app: Flask, provider: ActionProvider, eval_rate_store: object | None = None) -> None:
    """Register evaluation listing and creation routes."""

    @app.get("/api/evaluations")
    def list_evaluations() -> Response:
        raw_limit = request.args.get("limit", 0, type=int)
        if raw_limit <= 0 or raw_limit > _EVALUATIONS_LIST_HARD_CAP:
            limit = _EVALUATIONS_LIST_HARD_CAP
        else:
            limit = raw_limit
        state_arg = request.args.get("state", "").strip()
        states = {s for s in (v.strip() for v in state_arg.split(",")) if s} or None
        items = provider.list_evaluations(limit=limit, reports_dir=_reports_dir(), states=states)
        return jsonify([to_camel_dict(j) for j in items])

    @app.get("/api/evaluations/active")
    def get_active_evaluation() -> Response:
        """Return the first non-stale running evaluation job, or JSON null.

        Single authoritative answer to "is an evaluation actually running":
        the staleness rule lives in services.active_evaluation, so shells
        (native window, frontend) consume it instead of re-deriving it.
        """
        job = find_active_evaluation(provider, _reports_dir())
        return jsonify(to_camel_dict(job) if job is not None else None)

    @app.post("/api/evaluations")
    def start_evaluation() -> Response | tuple[Response, int]:
        rate_error = _check_eval_rate_limit(eval_rate_store)
        if rate_error is not None:
            return rate_error
        payload = request.get_json(silent=True) or {}
        error = _validate_start_payload(payload)
        if error is not None:
            return error
        repo = payload.get("repo")
        _logger.info("start_evaluation: repo=%s, remote_addr=%s", _sanitize_url(repo), request.remote_addr)
        try:
            options = _build_evaluation_options(payload)
        except ValueError as exc:
            body, status = error_response(str(exc), HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        # Same allowlist as /api/scan and POST /api/projects: starting an
        # evaluation registers + scans the directory and persists its file
        # tree, so an unvalidated local path would leak arbitrary readable
        # directories through project endpoints.
        try:
            is_url = is_repo_url(str(repo))
        except ValueError:
            body, status = error_response("Invalid repo URL", HTTPStatus.BAD_REQUEST, "INVALID_REPO_URL")
            return jsonify(body), status
        if not is_url:
            err = scan_target_error(str(repo), _reports_dir())
            if err is not None:
                body, status = err
                return jsonify(body), status
        try:
            job = provider.start_evaluation(repo=repo, reports_dir=_reports_dir(), options=options)
        except (FileNotFoundError, ValueError):
            body, status = error_response(
                "Invalid repository. Provide a local path or a URL like https://github.com/owner/repo.",
                HTTPStatus.BAD_REQUEST, "INVALID_INPUT",
            )
            return jsonify(body), status
        return jsonify(to_camel_dict(job)), HTTPStatus.ACCEPTED
