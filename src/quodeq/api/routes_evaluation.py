"""Evaluation listing, creation, status, and cancellation routes."""
from __future__ import annotations

import logging
from http import HTTPStatus

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response, validate_evaluation_payload
from quodeq.core.types import to_camel_dict
from quodeq.services.base import ActionProvider
from quodeq.services.tooling_mixin import get_allowed_client_ids as _get_allowed_ai_cmds
from quodeq.services.base import _DEFAULT_MAX_SUBAGENTS, _DEFAULT_POOL_BUDGET

_CREDENTIALS_RE = __import__("re").compile(r"(https?://)([^@]+)@")
_logger = logging.getLogger(__name__)

# Bounds for user-supplied evaluation parameters
_MIN_SUBAGENTS = 1
_MAX_SUBAGENTS = 10
_MIN_POOL_BUDGET = 60
_MAX_POOL_BUDGET = 3600


def _sanitize_url(url: str) -> str:
    """Remove embedded credentials from a URL for safe logging/error messages."""
    return _CREDENTIALS_RE.sub(r"\1***@", url)


def _validate_ai_cmd(ai_cmd: str | None, env: dict[str, str] | None = None) -> tuple[Response, int] | None:
    """Return an error response if *ai_cmd* is not in the allow-list, or None if valid."""
    if not ai_cmd:
        return None
    allowed_cmds = _get_allowed_ai_cmds(env=env)
    if ai_cmd not in allowed_cmds:
        allowed_list = ", ".join(sorted(allowed_cmds))
        body, status = error_response(
            f"Invalid AI command. Allowed: {allowed_list}",
            HTTPStatus.BAD_REQUEST,
            "INVALID_INPUT",
        )
        return jsonify(body), status
    return None


def _build_evaluation_options(payload: dict) -> "EvaluationOptions":
    """Construct and validate EvaluationOptions from the request payload."""
    from quodeq.services.base import EvaluationOptions  # deferred: avoid circular import at module level
    max_subagents_raw = payload.get("maxSubagents", _DEFAULT_MAX_SUBAGENTS)
    max_subagents = max(_MIN_SUBAGENTS, min(_MAX_SUBAGENTS, int(max_subagents_raw)))
    pool_budget_raw = payload.get("poolBudget", _DEFAULT_POOL_BUDGET)
    pool_budget = max(_MIN_POOL_BUDGET, min(_MAX_POOL_BUDGET, int(pool_budget_raw)))
    return EvaluationOptions(
        discipline=payload.get("discipline"),
        dimensions=payload.get("dimensions") or "",
        numerical=bool(payload.get("numerical")),
        ai_cmd=payload.get("aiCmd") or None,
        ai_model=payload.get("aiModel") or None,
        subagent_model=payload.get("subagentModel") or None,
        verify_findings=bool(payload.get("verifyFindings", True)),
        max_subagents=max_subagents,
        pool_budget=pool_budget,
        incremental=bool(payload.get("incremental", False)),
    )


def _check_eval_rate_limit(eval_rate_store: object | None) -> tuple[Response, int] | None:
    """Return an error response if the evaluation rate limit is exceeded, or None."""
    if eval_rate_store is None:
        return None
    import time as _time
    ip = request.remote_addr or "unknown"
    now = _time.monotonic()
    if eval_rate_store.check(ip, now):  # type: ignore[union-attr]
        body, status = error_response(
            "Too many evaluation requests", HTTPStatus.TOO_MANY_REQUESTS, "RATE_LIMITED",
        )
        return jsonify(body), status
    eval_rate_store.record(ip, now)  # type: ignore[union-attr]
    return None


def register_evaluation_list_routes(app: Flask, provider: ActionProvider, eval_rate_store: object | None = None) -> None:
    """Register evaluation listing and creation routes."""
    from quodeq.api.routes import _reports_dir

    @app.get("/api/evaluations")
    def list_evaluations() -> Response:
        return jsonify([to_camel_dict(j) for j in provider.list_evaluations()])

    @app.post("/api/evaluations")
    def start_evaluation() -> Response | tuple[Response, int]:
        rate_error = _check_eval_rate_limit(eval_rate_store)
        if rate_error is not None:
            return rate_error
        payload = request.get_json(silent=True) or {}
        validation_error = validate_evaluation_payload(payload)
        if validation_error:
            body, status = error_response(validation_error, HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        ai_cmd = payload.get("aiCmd") or None
        ai_cmd_error = _validate_ai_cmd(ai_cmd)
        if ai_cmd_error is not None:
            return ai_cmd_error
        repo = payload.get("repo")
        _logger.info("start_evaluation: repo=%s, remote_addr=%s", _sanitize_url(repo), request.remote_addr)
        try:
            options = _build_evaluation_options(payload)
            job = provider.start_evaluation(repo=repo, reports_dir=_reports_dir(), options=options)
        except (FileNotFoundError, ValueError):
            body, status = error_response("Invalid repository", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        return jsonify(to_camel_dict(job)), HTTPStatus.ACCEPTED


def register_evaluation_item_routes(app: Flask, provider: ActionProvider) -> None:
    """Register single-evaluation status and cancel routes."""

    @app.get("/api/evaluations/<job_id>")
    def get_evaluation(job_id: str) -> Response | tuple[Response, int]:
        job = provider.get_evaluation_status(job_id)
        if not job:
            body, status = error_response("Job not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(to_camel_dict(job))

    @app.delete("/api/evaluations/<job_id>")
    def cancel_evaluation(job_id: str) -> Response | tuple[Response, int]:
        _logger.info("cancel_evaluation: job_id=%s, remote_addr=%s", job_id, request.remote_addr)
        ok = provider.cancel_evaluation(job_id)
        if not ok:
            body, status = error_response("Job not found or not running", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify({"ok": True})
