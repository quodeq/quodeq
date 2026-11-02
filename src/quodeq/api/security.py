"""Security middleware: authentication, CSRF protection, rate limiting, and headers."""

from __future__ import annotations

import hmac
import logging
import re
import time
from collections.abc import Mapping
from http import HTTPStatus

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import SecurityError

from quodeq.api._constants import CODE_FORBIDDEN
from quodeq.api._rate_limit import RateLimitStore
from quodeq.api.session_auth import (  # noqa: F401  publish_session: app.main's entry
    check_session, install_session_auth, is_trusted_webview, publish_session,
)
from quodeq.api.helpers import json_error
from quodeq.api.routes_common import is_local_request
from quodeq.shared import request_metrics
from quodeq.shared.constants import SECRET_SUFFIX_CHARS
from quodeq.shared.dashboard_ports import alt_port_origins
from quodeq.shared.log_throttle import LogThrottle

_logger = logging.getLogger(__name__)

_HEALTH_PATH = "/api/health"
_RATE_LIMITED_GET_PATHS = frozenset({"/api/browse"})
# Per-finding user actions are idempotent and don't trigger expensive work
# server-side. Burst-dismissing is a normal user flow on large projects; a
# rate limit there just rolls back the optimistic UI update, which the user
# experiences as "violations come back". The global limit still applies to
# everything else (e.g. /api/evaluations/start).
_RATE_LIMIT_EXEMPT_PATHS = frozenset({
    "/api/findings/dismiss",
    "/api/findings/restore",
    "/api/findings/delete",
})
_SAFE_HTTP_METHODS = ("GET", "HEAD", "OPTIONS")  # never state-changing: skip CSRF + most rate limiting
_BEARER_PREFIX = "Bearer "
_MIN_BEARER_HEADER_LEN = len(_BEARER_PREFIX) + SECRET_SUFFIX_CHARS

# The desktop window's UA carries this launch's session secret, which also
# grants it 'unsafe-eval' for pywebview's new Function() JS bridge; see
# quodeq.api.session_auth.is_trusted_webview. The bare "QuodeqDesktop" UA
# marker is a public string and grants nothing.


# Host header must look like a bare hostname/IPv4 or a bracketed IPv6
# literal (RFC 3986 host syntax, e.g. "[::1]:7863"), with an optional port,
# before it's trusted enough to interpolate into the CSP connect-src
# directive. Rejects quotes, whitespace, and other characters that could
# inject extra CSP directives or sources via a spoofed Host header.
# The IPv6 branch matters here: ::1 is a first-class local address elsewhere
# in this app (routes_common.LOCALHOST_ADDRS, dashboard/_networking.py,
# dashboard/_webview_window_native_ops.py's reload allowlist), so a client
# reaching this dashboard over IPv6 loopback is a real access path, not a
# hypothetical.
_VALID_HOST_RE = re.compile(r"^(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])(:\d+)?$")

# connect-src alt-port origins probed by useServerHealth.js's
# altPortCandidates()/PORT_SCAN_SPAN (shared/dashboard_ports.py). CSP has no
# port wildcard so each origin is enumerated explicitly. Loopback addresses
# only, so cross-site exfil to external attackers is still blocked. The
# currentPort..+4 neighbourhood useServerHealth also probes for a non-default
# QUODEQ_DASHBOARD_PORT stays uncovered here beyond 'self'. Depends on no
# request data, so it is built once here instead of on every response.
_ALT_PORT_ORIGINS = alt_port_origins()

# Cooldown between consecutive "CSP same-origin ws computation failed" log
# lines. This except block sits in after_request, so it runs on every
# response; if the computation starts failing under some sustained condition
# we still want the FIRST occurrence surfaced immediately, but must not turn a
# per-request code path into a per-request log line -- that would make the
# failure itself a new source of log-volume noise. The LogThrottle instance
# lives per-app (created in configure_security); shared/log_throttle.py has
# the lock-free rationale.
_CSP_WS_FAILURE_LOG_INTERVAL_S = 60.0


def _check_auth(api_key: str | None) -> Response | tuple[Response, int] | None:
    """Verify API key authentication when *api_key* is set.

    Security model:
    - With API key: Bearer token required on all non-health requests.
    - Without API key: only localhost requests are permitted (defense-in-depth
      with CSRF Origin check for state-changing methods).  Set
      ``QUODEQ_API_KEY`` for any non-localhost deployment.
    """
    if request.path == _HEALTH_PATH:
        return None
    if api_key:
        auth = request.headers.get("Authorization", "")
        # compare_digest raises TypeError on non-ASCII str input.
        if not auth.isascii() or not hmac.compare_digest(auth, f"{_BEARER_PREFIX}{api_key}"):
            return json_error("Unauthorized", HTTPStatus.UNAUTHORIZED, "UNAUTHORIZED")
    else:
        if not is_local_request():
            return jsonify({
                "error": "Set QUODEQ_API_KEY to allow remote access",
                "code": "UNAUTHORIZED",
            }), HTTPStatus.UNAUTHORIZED
    return None


def _check_csrf() -> Response | tuple[Response, int] | None:
    """Verify Origin header on state-changing requests."""
    if request.method in _SAFE_HTTP_METHODS:
        return None
    origin = request.headers.get("Origin")
    if not origin:
        return json_error("Origin header required", HTTPStatus.FORBIDDEN, CODE_FORBIDDEN)
    allowed = {f"http://{request.host}", f"https://{request.host}"}
    if origin not in allowed:
        return json_error("Origin not allowed", HTTPStatus.FORBIDDEN, CODE_FORBIDDEN)
    return None


def _check_rate_limit(store: RateLimitStore) -> Response | tuple[Response, int] | None:
    """Enforce rate limiting on state-changing requests and sensitive GET endpoints."""
    if request.method in _SAFE_HTTP_METHODS and request.path not in _RATE_LIMITED_GET_PATHS:
        return None
    if request.path in _RATE_LIMIT_EXEMPT_PATHS:
        return None
    return _count_attempt(store)


def _count_attempt(store: RateLimitStore) -> Response | tuple[Response, int] | None:
    """Record one attempt for this client; a 429 once it is over the cap."""
    ip = request.remote_addr or "unknown"
    now = time.monotonic()
    if hasattr(store, "check_and_record"):
        limited = store.check_and_record(ip, now)
    else:
        # Back-compat: external RateLimitStore implementers written against
        # the old check()/record() Protocol don't have check_and_record.
        limited = store.check(ip, now)
        if not limited:
            store.record(ip, now)
    if limited:
        return json_error("Too many requests", HTTPStatus.TOO_MANY_REQUESTS, "RATE_LIMITED")
    return None


def _same_origin_ws_sources(host: str) -> str:
    """Build the same-origin ``ws:``/``wss:`` connect-src entry for *host*.

    *host* is the raw, attacker-controlled Host header (``request.host``).
    It's only interpolated into the CSP when it matches a bare
    ``hostname[:port]`` shape; otherwise the same-origin entry is omitted
    (the alt-port origins already in connect-src still cover local
    dev/desktop use) rather than reflecting attacker-controlled bytes into
    a security header.
    """
    if not _VALID_HOST_RE.match(host):
        return ""
    return f"ws://{host} wss://{host}"


def _actor(api_key: str | None) -> str:
    if api_key:
        auth = request.headers.get("Authorization", "")
        if auth.startswith(_BEARER_PREFIX) and len(auth) > _MIN_BEARER_HEADER_LEN:
            return f" (actor=key:***{auth[-SECRET_SUFFIX_CHARS:]})"
    return ""


def _log_csp_ws_failure(exc: Exception, throttle: LogThrottle) -> None:
    """Surface a same-origin ws CSP computation failure, rate-limited.

    Runs inside ``after_request`` on every response, so this must never
    raise and must never become an unbounded log source on its own: only
    the exception's type name is logged (no header/request content, so
    nothing attacker-controlled reaches the log line), and repeats within
    *throttle*'s interval are dropped. A failing handler is the handler's
    problem (stdlib handleError contract); this module does not control
    its logger's handlers, and ``_add_security_headers`` already logs
    unguarded on every request, so a guard here never covered the real
    risk.
    """
    if not throttle.should_emit(time.monotonic()):
        return
    _logger.warning(
        "CSP same-origin ws/wss connect-src computation failed (%s); "
        "omitting that entry for this response (further repeats "
        "suppressed for %ss)",
        type(exc).__name__,
        _CSP_WS_FAILURE_LOG_INTERVAL_S,
    )


def configure_security(
    app: Flask,
    rate_limit_store: RateLimitStore,
    api_key: str | None,
    env: Mapping[str, str] | None = None,
) -> None:
    """Register before/after request hooks for auth, CSRF, rate-limiting, and security headers.

    Without *api_key* every request must also carry this launch's session
    secret (``session_auth``); *env* names the port its cookie is keyed by.
    """
    csp_ws_failure_throttle = LogThrottle(_CSP_WS_FAILURE_LOG_INTERVAL_S)
    session = install_session_auth(app, env)

    @app.before_request
    def _security_checks() -> Response | tuple[Response, int] | None:
        denied = _check_auth(api_key) or (None if api_key else check_session(session))
        if denied is not None:
            # A failed auth always counts, whatever the method or path, so
            # key guessing hits the limit. Passing requests are unaffected.
            return _count_attempt(rate_limit_store) or denied
        # The session header cannot come from a cross-site page, so it needs no Origin.
        csrf = None if session.header_ok() else _check_csrf()
        return csrf or _check_rate_limit(rate_limit_store)

    @app.after_request
    def _add_security_headers(response: Response) -> Response:
        _logger.info(
            "API: %s %s%s -> %d%s", request.method, request.path, _actor(api_key), response.status_code,
            request_metrics.log_suffix(),
        )
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        # The primary bind port isn't known here; add same-origin ws explicitly.
        try:
            self_ws = _same_origin_ws_sources(request.host)
        except SecurityError as exc:
            self_ws = ""
            _log_csp_ws_failure(exc, csp_ws_failure_throttle)
        is_webview = is_trusted_webview(request.headers.get("User-Agent", ""), session.secret)
        script_src = "script-src 'self' 'unsafe-eval'" if is_webview else "script-src 'self'"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"connect-src 'self' {_ALT_PORT_ORIGINS} {self_ws}; "
            f"{script_src}; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "mask-src 'self' data:; "
            "frame-ancestors 'none'"
        )
        return response
