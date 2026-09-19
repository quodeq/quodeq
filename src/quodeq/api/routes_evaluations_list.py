"""Evaluation listing, active-evaluation lookup, and creation routes."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from flask import Flask, Response, jsonify, request

from quodeq.api._evaluation_helpers import (
    InvalidEvaluationOption,
    _check_eval_rate_limit,
    _sanitize_url,
    _validate_ai_cmd,
    _validate_ai_cmd_path,
    _validate_ai_model,
    clean_scan_conflict_error,
)
from quodeq.api._evaluation_options import _build_evaluation_options
from quodeq.api.helpers import json_error, page_params, scan_target_error, validate_evaluation_payload
from quodeq.shared.serialization import to_camel_dict
from quodeq.shared.validation import relative_scope_error
from quodeq.assistant import get_provider_configs
from quodeq.api.routes_common import reports_dir
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
        return json_error(validation_error, HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
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


@dataclass(frozen=True)
class _StartRequest:
    """A validated POST /api/evaluations body, ready for provider.start_evaluation."""

    repo: Any
    options: Any


def _pre_build_options_error(payload: dict) -> tuple[Response, int] | None:
    """Pre-check every ValueError source ``_build_evaluation_options`` can
    hit today (clean_scan conflict, then scope path -- same order it checks
    them internally), so the caller's try/except is an unreachable safety
    net, never a path that has to echo exception text."""
    conflict_err = clean_scan_conflict_error(payload)
    if conflict_err is not None:
        return json_error(conflict_err, HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
    scope_path = payload.get("scopePath") or None
    if scope_path is not None:
        err = relative_scope_error(str(scope_path))
        if err is not None:
            return json_error(err, HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
    return None


def _build_options_or_error(payload: dict) -> tuple[Any, tuple[Response, int] | None]:
    """Pre-check then build the evaluation options. Returns ``(options, error)``."""
    pre_error = _pre_build_options_error(payload)
    if pre_error is not None:
        return None, pre_error
    try:
        return _build_evaluation_options(payload), None
    except InvalidEvaluationOption as exc:
        # exc.public_message, not str(exc): the field-naming text an
        # InvalidEvaluationOption carries is written by coerce_int itself,
        # names only the field, and interpolates nothing from the request
        # (never raw exception formatting), so it is safe to return verbatim.
        return None, json_error(exc.public_message, HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
    except ValueError:
        # Constant message, not str(exc): every other raise source is
        # pre-checked above. Keep it unbound so nothing here can ever echo
        # exception text.
        return None, json_error(
            "Invalid evaluation options", HTTPStatus.BAD_REQUEST, "INVALID_INPUT",
        )


def _repo_target_error(repo: Any) -> tuple[Response, int] | None:
    """Reject a repo that is neither a valid URL nor an allowlisted local path.

    Same allowlist as /api/scan and POST /api/projects: starting an
    evaluation registers + scans the directory and persists its file
    tree, so an unvalidated local path would leak arbitrary readable
    directories through project endpoints.
    """
    try:
        is_url = is_repo_url(str(repo))
    except ValueError:
        return json_error("Invalid repo URL", HTTPStatus.BAD_REQUEST, "INVALID_REPO_URL")
    if is_url:
        return None
    err = scan_target_error(str(repo), reports_dir())
    if err is None:
        return None
    body, status = err
    return jsonify(body), status


def _validated_start_request(
    payload: dict,
) -> tuple[_StartRequest | None, Response | tuple[Response, int] | None]:
    """Validate + build a start request. Returns ``(request, error)``: on
    success *error* is None; on failure *request* is None and *error* is the
    route's early-return value.
    """
    error = _validate_start_payload(payload)
    if error is not None:
        return None, error
    repo = payload.get("repo")
    _logger.info("start_evaluation: repo=%s, remote_addr=%s", _sanitize_url(repo), request.remote_addr)
    options, options_error = _build_options_or_error(payload)
    if options_error is not None:
        return None, options_error
    target_error = _repo_target_error(repo)
    if target_error is not None:
        return None, target_error
    return _StartRequest(repo=repo, options=options), None


def register_evaluation_list_routes(app: Flask, provider: ActionProvider, eval_rate_store: object | None = None) -> None:
    """Register evaluation listing and creation routes."""

    @app.get("/api/evaluations")
    def list_evaluations() -> Response | tuple[dict[str, Any], int]:
        # limit=0 is this route's "no client cap" sentinel, so 0 stays valid;
        # a malformed or negative value answers 400 (see page_params). The
        # hard cap stays a clamp below.
        paging = page_params(request.args, default_limit=0, min_limit=0)
        if isinstance(paging[0], dict):
            return paging
        raw_limit = paging[0]
        if raw_limit <= 0 or raw_limit > _EVALUATIONS_LIST_HARD_CAP:
            limit = _EVALUATIONS_LIST_HARD_CAP
        else:
            limit = raw_limit
        state_arg = request.args.get("state", "").strip()
        states = {s for s in (v.strip() for v in state_arg.split(",")) if s} or None
        items = provider.list_evaluations(limit=limit, reports_dir=reports_dir(), states=states)
        return jsonify([to_camel_dict(j) for j in items])

    @app.get("/api/evaluations/active")
    def get_active_evaluation() -> Response:
        """Return the first non-stale running evaluation job, or JSON null.

        Single authoritative answer to "is an evaluation actually running":
        the staleness rule lives in services.active_evaluation, so shells
        (native window, frontend) consume it instead of re-deriving it.
        """
        job = find_active_evaluation(provider, reports_dir())
        return jsonify(to_camel_dict(job) if job is not None else None)

    @app.post("/api/evaluations")
    def start_evaluation() -> Response | tuple[Response, int]:
        rate_error = _check_eval_rate_limit(eval_rate_store)
        if rate_error is not None:
            return rate_error
        payload = request.get_json(silent=True) or {}
        start_request, error = _validated_start_request(payload)
        if error is not None:
            return error
        try:
            job = provider.start_evaluation(
                repo=start_request.repo, reports_dir=reports_dir(), options=start_request.options,
            )
        except (FileNotFoundError, ValueError):
            return json_error(
                "Invalid repository. Provide a local path or a URL like https://github.com/owner/repo.",
                HTTPStatus.BAD_REQUEST, "INVALID_INPUT",
            )
        return jsonify(to_camel_dict(job)), HTTPStatus.ACCEPTED
