"""Validation and helper functions for evaluation routes."""
from __future__ import annotations

import logging
from http import HTTPStatus

from flask import Response, jsonify, request

from quodeq.api.helpers import error_response
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
