"""Security middleware: authentication, CSRF protection, rate limiting, and headers."""

from __future__ import annotations

import hmac
import logging
import time
from http import HTTPStatus

from flask import Flask, Response, jsonify, request

from quodeq.api._rate_limit import RateLimitStore

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
_LOCALHOST_ADDRS = {"127.0.0.1", "::1"}


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
        if not hmac.compare_digest(auth, f"Bearer {api_key}"):
            return jsonify({"error": "Unauthorized", "code": "UNAUTHORIZED"}), HTTPStatus.UNAUTHORIZED
    else:
        remote = request.remote_addr or ""
        if remote not in _LOCALHOST_ADDRS:
            return jsonify({
                "error": "Set QUODEQ_API_KEY to allow remote access",
                "code": "UNAUTHORIZED",
            }), HTTPStatus.UNAUTHORIZED
    return None


def _check_csrf() -> Response | tuple[Response, int] | None:
    """Verify Origin header on state-changing requests."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    origin = request.headers.get("Origin")
    if not origin:
        return jsonify({"error": "Origin header required", "code": "FORBIDDEN"}), HTTPStatus.FORBIDDEN
    allowed = {f"http://{request.host}", f"https://{request.host}"}
    if origin not in allowed:
        return jsonify({"error": "Origin not allowed", "code": "FORBIDDEN"}), HTTPStatus.FORBIDDEN
    return None


def _check_rate_limit(store: RateLimitStore) -> Response | tuple[Response, int] | None:
    """Enforce rate limiting on state-changing requests and sensitive GET endpoints."""
    if request.method in ("GET", "HEAD", "OPTIONS") and request.path not in _RATE_LIMITED_GET_PATHS:
        return None
    if request.path in _RATE_LIMIT_EXEMPT_PATHS:
        return None
    ip = request.remote_addr or "unknown"
    now = time.monotonic()
    if store.check(ip, now):
        return jsonify({"error": "Too many requests", "code": "RATE_LIMITED"}), HTTPStatus.TOO_MANY_REQUESTS
    store.record(ip, now)
    return None


def configure_security(app: Flask, rate_limit_store: RateLimitStore, api_key: str | None) -> None:
    """Register before/after request hooks for auth, CSRF, rate-limiting, and security headers."""

    @app.before_request
    def _audit_log() -> None:
        actor = ""
        if api_key:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer ") and len(auth) > 11:
                actor = f" (actor=key:***{auth[-4:]})"
        _logger.info("API: %s %s%s", request.method, request.path, actor)

    @app.before_request
    def _security_checks() -> Response | tuple[Response, int] | None:
        return _check_auth(api_key) or _check_csrf() or _check_rate_limit(rate_limit_store)

    @app.after_request
    def _add_security_headers(response: Response) -> Response:
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        # connect-src: include alt-port origins probed by useServerHealth
        # (DEFAULT_ALT_PORTS = [4180, 4181, 4182, 4183] in useServerHealth.js).
        # CSP has no port wildcard so each origin is enumerated explicitly.
        # These are loopback addresses only — cross-site exfil to external
        # attackers is still blocked.
        _alt_port_origins = " ".join(
            f"http://127.0.0.1:{p} http://localhost:{p}"
            for p in (4180, 4181, 4182, 4183)
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"connect-src 'self' {_alt_port_origins}; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "mask-src 'self' data:; "
            "frame-ancestors 'none'"
        )
        return response
