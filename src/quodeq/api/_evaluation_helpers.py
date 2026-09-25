"""Validation and helper functions for evaluation routes."""
from __future__ import annotations

import logging
import time as _time
from collections.abc import Mapping
from http import HTTPStatus
from typing import TYPE_CHECKING

from flask import Response, request

from quodeq.api.helpers import ClientMessageError, json_error
from quodeq.services.tooling_mixin import get_allowed_client_ids as _get_allowed_ai_cmds
from quodeq.shared.cmd_path_policy import ai_cmd_path_error  # noqa: F401 — re-export/patch target
from quodeq.shared.repo import split_userinfo

if TYPE_CHECKING:
    from quodeq.api._rate_limit import RateLimitStore

_logger = logging.getLogger(__name__)


def clean_scan_conflict_error(payload: dict) -> str | None:
    """Return an error message if *payload* sends both the new ``cleanScan``
    field and the deprecated ``incremental`` field, else None. Message text
    mirrors :func:`resolve_clean_scan` exactly."""
    if "cleanScan" in payload and "incremental" in payload:
        return (
            "`cleanScan` and `incremental` cannot be combined in a single payload. "
            "Use `cleanScan` only -- `incremental` is deprecated. "
            "Send `cleanScan: false` (use cached findings, default) or `cleanScan: true` "
            "(force full re-analysis)."
        )
    return None


def resolve_clean_scan(payload: dict) -> bool:
    """Resolve the user's clean_scan intent from new and legacy fields.

    New: ``cleanScan: bool`` -- explicit opt-out, default False.
    Legacy: ``incremental: bool`` -- deprecated, with inverted semantics
    (old ``True`` meant "use cache" -> ``clean_scan=False``; old ``False``
    meant "ignore cache" -> ``clean_scan=True``). One-release back-compat.

    Sending both is rejected: we won't guess intent if a client transitions
    mid-deployment and ends up posting conflicting flags.
    """
    err = clean_scan_conflict_error(payload)
    if err is not None:
        raise ValueError(err)
    has_legacy = "incremental" in payload
    if has_legacy:
        _logger.warning(
            "Evaluation payload uses deprecated `incremental` field. "
            "Migrate to `cleanScan` (inverted semantics). "
            "Legacy field will be removed in the next release.",
        )
        return not bool(payload.get("incremental"))
    return bool(payload.get("cleanScan", False))


class InvalidEvaluationOption(ClientMessageError, ValueError):
    """A present-but-malformed evaluation option; ``public_message`` is the
    field-naming text a route may return to the client verbatim.

    Also a ValueError so the routes' existing ``except ValueError`` guards
    around option building still catch it.
    """


def coerce_int(value: object, default: int, field: str) -> int:
    """Return int(*value*) when convertible; *default* when *value* is
    ``None`` (absent) or a blank/whitespace-only string. Raises
    ``InvalidEvaluationOption`` naming *field* when *value* is present but
    not convertible to int, so a malformed override surfaces as a 400
    instead of silently falling back to the default.

    The message names the field only, never the received value: this text
    reaches the client verbatim (see _build_options_or_error), and the
    routes hold the invariant that no request input is reflected back in a
    response. The caller knows what they sent; the field name is the part
    they cannot see.

    A blank string counts as absent: that is how a cleared form field
    arrives, and it meant "use the default" before this validation existed.
    """
    if value is None:
        return default
    if isinstance(value, str) and not value.strip():
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidEvaluationOption(f"{field} must be an integer") from exc


def sanitize_url(url: str) -> str:
    """Remove embedded credentials from a URL for safe logging/error messages.

    The userinfo is masked as ``***@``. ``split_userinfo`` documents how the
    credential boundary is found.
    """
    parts = split_userinfo(url)
    if parts is None:
        return url
    scheme, after = parts
    return f"{scheme}***@{after}"


def validate_ai_cmd(ai_cmd: str | None, env: dict[str, str] | None = None) -> tuple[Response, int] | None:
    """Return an error response if *ai_cmd* is not in the allow-list, or None if valid."""
    if not ai_cmd:
        return None
    allowed_cmds = _get_allowed_ai_cmds(env=env)
    if ai_cmd not in allowed_cmds:
        allowed_list = ", ".join(sorted(allowed_cmds))
        return json_error(
            f"Invalid AI command. Allowed: {allowed_list}",
            HTTPStatus.BAD_REQUEST,
            "INVALID_INPUT",
        )
    return None


def validate_ai_model(
    ai_cmd: str | None, ai_model: str | None, provider_configs: Mapping[str, dict],
) -> tuple[Response, int] | None:
    """API-type providers require an explicit model."""
    if ai_cmd and provider_configs.get(ai_cmd, {}).get("type") == "api" and not ai_model:
        return json_error(
            "No model selected. Go to Settings and select one.",
            HTTPStatus.BAD_REQUEST, "MODEL_REQUIRED",
        )
    return None


def validate_ai_cmd_path(
    ai_cmd: str | None, ai_cmd_path: str | None,
) -> tuple[Response, int] | None:
    """Return a 400 error response if *ai_cmd_path* is not an acceptable
    binary override for provider *ai_cmd*, or None if valid (or absent).
    Rules live in ai_cmd_path_error."""
    reason = ai_cmd_path_error(ai_cmd, ai_cmd_path)
    if reason is None:
        return None
    return json_error(
        f"Invalid AI command override: {reason}",
        HTTPStatus.BAD_REQUEST,
        "INVALID_INPUT",
    )


def check_eval_rate_limit(eval_rate_store: "RateLimitStore | None") -> tuple[Response, int] | None:
    """Return an error response if the evaluation rate limit is exceeded, or None."""
    if eval_rate_store is None:
        return None
    ip = request.remote_addr or "unknown"
    now = _time.monotonic()
    if eval_rate_store.check(ip, now):
        return json_error(
            "Too many evaluation requests", HTTPStatus.TOO_MANY_REQUESTS, "RATE_LIMITED",
        )
    eval_rate_store.record(ip, now)
    return None
