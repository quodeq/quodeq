"""Request-context gating shared by every terminal route.

The two reasons differ only in whether Origin is checked; see
``quodeq.terminal.gate`` for the policy itself.
"""
from __future__ import annotations

import functools
from collections.abc import Callable
from http import HTTPStatus

from flask import current_app, request

from quodeq.api._constants import CODE_FORBIDDEN
from quodeq.api.helpers import json_error
from quodeq.terminal.gate import terminal_env_reason, terminal_gate_reason


def env_reason() -> str | None:
    # Environment availability only (no Origin) — for /status, a same-origin
    # GET the browser sends WITHOUT an Origin header. Gating it on Origin would
    # wrongly report the terminal disabled ("Missing Origin header").
    return terminal_env_reason(
        host=current_app.config.get("QUODEQ_BIND_HOST", ""),
        api_key=current_app.config.get("QUODEQ_API_KEY"),
        request_host=request.host,
    )


def gate_reason() -> str | None:
    # Full gate incl. Origin — for the WS handshake (browsers DO send Origin on
    # WS) and the /kill POST (Origin also enforced by the global CSRF hook).
    return terminal_gate_reason(
        host=current_app.config.get("QUODEQ_BIND_HOST", ""),
        api_key=current_app.config.get("QUODEQ_API_KEY"),
        origin=request.headers.get("Origin"),
        request_host=request.host,
    )


def forbidden():
    return json_error("forbidden", HTTPStatus.FORBIDDEN, CODE_FORBIDDEN)


def gated(reason: Callable[[], str | None] = gate_reason):
    """Decorate a terminal HTTP handler so it answers 403 when *reason* refuses.

    *reason* defaults to the full gate (Origin included); the listing route
    passes ``env_reason``. The handler runs only when *reason* returns None.
    """
    def decorate(handler):
        @functools.wraps(handler)
        def guarded(*args, **kwargs):
            if reason() is not None:
                return forbidden()
            return handler(*args, **kwargs)
        return guarded
    return decorate
