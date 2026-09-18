"""Request-context gating shared by every terminal route.

Split out of ``terminal_routes.py`` to keep that module under the size limit.
The two reasons differ only in whether Origin is checked; see
``quodeq.terminal.gate`` for the policy itself.
"""
from __future__ import annotations

from flask import current_app, request

from quodeq.api.helpers import json_error
from quodeq.terminal.gate import terminal_env_reason, terminal_gate_reason


def _env_reason() -> str | None:
    # Environment availability only (no Origin) — for /status, a same-origin
    # GET the browser sends WITHOUT an Origin header. Gating it on Origin would
    # wrongly report the terminal disabled ("Missing Origin header").
    return terminal_env_reason(
        host=current_app.config.get("QUODEQ_BIND_HOST", ""),
        api_key=current_app.config.get("QUODEQ_API_KEY"),
        request_host=request.host,
    )


def _gate_reason() -> str | None:
    # Full gate incl. Origin — for the WS handshake (browsers DO send Origin on
    # WS) and the /kill POST (Origin also enforced by the global CSRF hook).
    return terminal_gate_reason(
        host=current_app.config.get("QUODEQ_BIND_HOST", ""),
        api_key=current_app.config.get("QUODEQ_API_KEY"),
        origin=request.headers.get("Origin"),
        request_host=request.host,
    )


def _forbidden():
    return json_error("forbidden", 403, "FORBIDDEN")  # code + message once, for six routes
