"""Validation and helper functions for evaluation routes."""
from __future__ import annotations

import os.path
import re
import shutil
import time as _time
from http import HTTPStatus

from flask import Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.services.tooling_mixin import get_allowed_client_ids as _get_allowed_ai_cmds
from quodeq.services.base import DEFAULT_MAX_SUBAGENTS, DEFAULT_TIME_LIMIT, resolve_clean_scan
from quodeq.shared.utils import get_ai_cmd as _get_ai_cmd
from quodeq.shared.validation import validate_relative_scope

# Userinfo cannot contain an unencoded "/", so excluding it keeps matches
# identical while a failing scan stays linear (no polynomial backtracking
# on inputs like repeated "http://" runs).
_CREDENTIALS_RE = re.compile(r"(https?://)([^/@]+)@")

# Bounds for user-supplied evaluation parameters
_MIN_SUBAGENTS = 1
_MAX_SUBAGENTS = 10
_MIN_TIME_LIMIT = 60
_MAX_TIME_LIMIT = 3600
_MAX_CONTEXT_SIZE = 2_000_000


def _coerce_int(value: object, default: int) -> int:
    """Return int(*value*) when convertible, else *default*. Never raises."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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


# Binary override charset: letters, digits, '.', '_', '-', ':' and path
# separators. No whitespace or shell metacharacters, matching the posture of
# shared.prereqs._SAFE_CMD_TOKEN_RE.
_SAFE_CMD_PATH_RE = re.compile(r"[A-Za-z0-9._/\\:-]+")


def _path_dirs(env: dict[str, str] | None = None) -> list[str]:
    """Real (symlink-resolved, case-normalized) directories on the server's PATH."""
    raw = (env or os.environ).get("PATH", "")
    return [os.path.normcase(os.path.realpath(d)) for d in raw.split(os.pathsep) if d]


def _validate_ai_cmd_path(
    ai_cmd: str | None, ai_cmd_path: str | None,
) -> tuple[Response, int] | None:
    """Return an error response if *ai_cmd_path* is not an acceptable binary
    override for provider *ai_cmd*, or None if valid (or absent).

    The aiCmd allow-list exists so the local HTTP API can never spawn an
    arbitrary binary. A free-text override would reopen that, so it must
    (a) contain no shell metacharacters or '..' segments, (b) be absolute
    when it names a path at all, (c) have a basename that starts with the
    provider id (e.g. 'claude-api' or '/opt/bin/claude-max' for 'claude'),
    (d) resolve to an existing executable, and (e) live in a directory on
    the server's PATH. (c) keeps the override an alternate install of the
    allowed CLI, (e) keeps it out of attacker-writable locations like /tmp
    or a downloads folder.
    """
    if not ai_cmd_path:
        return None

    def _invalid(reason: str) -> tuple[Response, int]:
        body, status = error_response(
            f"Invalid AI command override: {reason}",
            HTTPStatus.BAD_REQUEST,
            "INVALID_INPUT",
        )
        return jsonify(body), status

    if not _SAFE_CMD_PATH_RE.fullmatch(ai_cmd_path):
        return _invalid(
            "only letters, digits, '.', '_', '-', ':' and path separators are allowed"
        )
    normalized = ai_cmd_path.replace("\\", "/")
    if ".." in normalized.split("/"):
        return _invalid("'..' path segments are not allowed")
    if "/" in normalized and not os.path.isabs(ai_cmd_path):
        return _invalid("a path must be absolute; otherwise use a bare command name")
    provider = ai_cmd or _get_ai_cmd()
    basename = os.path.basename(normalized)
    if not basename.startswith(provider):
        return _invalid(f"binary name must start with '{provider}'")
    resolved = shutil.which(ai_cmd_path)
    if resolved is None:
        return _invalid(f"'{ai_cmd_path}' was not found or is not executable")
    resolved_dir = os.path.normcase(os.path.realpath(os.path.dirname(os.path.abspath(resolved))))
    if resolved_dir not in _path_dirs():
        return _invalid(
            f"'{ai_cmd_path}' is not in a directory on PATH; move it to one "
            f"(e.g. ~/.local/bin) or add its directory to PATH"
        )
    return None


def _build_evaluation_options(payload: dict) -> "EvaluationOptions":
    """Construct and validate EvaluationOptions from the request payload."""
    from quodeq.services.base import EvaluationOptions  # deferred: avoid circular import at module level
    max_subagents_raw = _coerce_int(payload.get("maxSubagents"), DEFAULT_MAX_SUBAGENTS)
    max_subagents = max(_MIN_SUBAGENTS, min(_MAX_SUBAGENTS, max_subagents_raw))
    # Read new key first; fall back to legacy `poolBudget` for back-compat.
    time_limit_raw = _coerce_int(
        payload.get("timeLimit", payload.get("poolBudget")), DEFAULT_TIME_LIMIT,
    )
    time_limit = 0 if time_limit_raw == 0 else max(_MIN_TIME_LIMIT, min(_MAX_TIME_LIMIT, time_limit_raw))
    ai_model = payload.get("aiModel") or None
    subagent_model = payload.get("subagentModel") or ai_model  # default to orchestrator
    clean_scan = resolve_clean_scan(payload)
    scope_path = payload.get("scopePath") or None
    if scope_path is not None:
        # ValueError propagates to the route's 400 INVALID_INPUT handler.
        validate_relative_scope(str(scope_path))
    return EvaluationOptions(
        discipline=payload.get("discipline"),
        dimensions=payload.get("dimensions") or "",
        numerical=bool(payload.get("numerical")),
        ai_cmd=payload.get("aiCmd") or None,
        ai_cmd_path=payload.get("aiCmdPath") or None,
        ai_model=ai_model,
        subagent_model=subagent_model,
        verify_findings=bool(payload.get("verifyFindings", True)),
        max_subagents=max_subagents,
        time_limit=time_limit,
        clean_scan=clean_scan,
        per_dimension=bool(payload.get("perDimension", False)),
        context_size=max(0, min(_MAX_CONTEXT_SIZE, _coerce_int(payload.get("contextSize"), 0))),
        branch=payload.get("branch") or None,
        scope_path=scope_path,
        provider_api_key=str(payload.get("apiKey") or ""),
        provider_api_base=str(payload.get("apiBase") or ""),
    )


def _check_eval_rate_limit(eval_rate_store: object | None) -> tuple[Response, int] | None:
    """Return an error response if the evaluation rate limit is exceeded, or None."""
    if eval_rate_store is None:
        return None
    ip = request.remote_addr or "unknown"
    now = _time.monotonic()
    if eval_rate_store.check(ip, now):  # type: ignore[union-attr]
        body, status = error_response(
            "Too many evaluation requests", HTTPStatus.TOO_MANY_REQUESTS, "RATE_LIMITED",
        )
        return jsonify(body), status
    eval_rate_store.record(ip, now)  # type: ignore[union-attr]
    return None
