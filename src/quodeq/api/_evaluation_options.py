"""Request payload -> EvaluationOptions.

Depends on ``_evaluation_helpers`` for the shared coercion primitives, never
the other way round.
"""
from __future__ import annotations

from typing import NamedTuple

from quodeq.api._evaluation_helpers import coerce_int, resolve_clean_scan
from quodeq.config.ai_provider import get_api_key_secure
from quodeq.core.utils.numbers import clamp
from quodeq.services.base import (
    DEFAULT_MAX_SUBAGENTS, DEFAULT_TIME_LIMIT, EvaluationOptions,
)
from quodeq.shared.validation import validate_relative_scope

# Bounds for user-supplied evaluation parameters
_MIN_SUBAGENTS = 1
_MAX_SUBAGENTS = 10
_MIN_TIME_LIMIT = 60
_MAX_TIME_LIMIT = 3600
_MAX_CONTEXT_SIZE = 2_000_000


class _Limits(NamedTuple):
    max_subagents: int
    time_limit: int


class _Flags(NamedTuple):
    ai_cmd: str | None
    ai_model: str | None
    subagent_model: str | None
    clean_scan: bool
    scope_path: str | None
    provider_api_key: str


def _parse_limits(body: dict) -> _Limits:
    """Clamp the numeric run limits from *body* to their allowed ranges."""
    subagents = coerce_int(body.get("maxSubagents"), DEFAULT_MAX_SUBAGENTS, "maxSubagents")
    # Read new key first; fall back to legacy `poolBudget` for back-compat.
    # The label is the key the client actually sent, so a malformed legacy
    # value is not reported against a field absent from the body.
    field = "poolBudget" if "poolBudget" in body and "timeLimit" not in body else "timeLimit"
    raw_limit = coerce_int(body.get("timeLimit", body.get("poolBudget")), DEFAULT_TIME_LIMIT, field)
    return _Limits(
        clamp(subagents, _MIN_SUBAGENTS, _MAX_SUBAGENTS),
        0 if raw_limit == 0 else clamp(raw_limit, _MIN_TIME_LIMIT, _MAX_TIME_LIMIT),
    )


def _parse_flags(body: dict) -> _Flags:
    """Resolve the *body* fields that need more than a direct read."""
    ai_model = body.get("aiModel") or None
    ai_cmd = body.get("aiCmd") or None
    clean_scan = resolve_clean_scan(body)
    scope_path = body.get("scopePath") or None
    if scope_path is not None:
        # ValueError propagates to the route's 400 INVALID_INPUT handler.
        validate_relative_scope(str(scope_path))
    provider_api_key = str(body.get("apiKey") or "")
    if not provider_api_key and ai_cmd:
        provider_api_key = get_api_key_secure(ai_cmd) or ""
    return _Flags(
        ai_cmd=ai_cmd,
        ai_model=ai_model,
        subagent_model=body.get("subagentModel") or ai_model,  # default to orchestrator
        clean_scan=clean_scan,
        scope_path=scope_path,
        provider_api_key=provider_api_key,
    )


def build_evaluation_options(payload: dict) -> EvaluationOptions:
    """Construct and validate EvaluationOptions from the request payload."""
    limits = _parse_limits(payload)
    flags = _parse_flags(payload)
    context_size = coerce_int(payload.get("contextSize"), 0, "contextSize")
    return EvaluationOptions(
        discipline=payload.get("discipline"),
        dimensions=payload.get("dimensions") or "",
        numerical=bool(payload.get("numerical")),
        ai_cmd=flags.ai_cmd,
        ai_cmd_path=payload.get("aiCmdPath") or None,
        ai_model=flags.ai_model,
        subagent_model=flags.subagent_model,
        verify_findings=bool(payload.get("verifyFindings", True)),
        max_subagents=limits.max_subagents,
        time_limit=limits.time_limit,
        clean_scan=flags.clean_scan,
        per_dimension=bool(payload.get("perDimension", False)),
        context_size=clamp(context_size, 0, _MAX_CONTEXT_SIZE),
        branch=payload.get("branch") or None,
        scope_path=flags.scope_path,
        provider_api_key=flags.provider_api_key,
        provider_api_base=str(payload.get("apiBase") or ""),
    )
