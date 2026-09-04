"""Security middleware: authentication, CSRF protection, rate limiting, and headers."""

from __future__ import annotations

import hmac
import logging
import re
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

# Marker substring in the native webview's User-Agent (set by
# quodeq.dashboard._webview_window). Requests carrying it are the trusted
# local desktop shell and are served 'unsafe-eval' so pywebview's
# new Function() JS bridge works; browsers keep the strict script-src.
# Loopback-only exposure: a local process could spoof this UA, but it
# would already have local code execution. The literal MUST match
# _webview_window._WEBVIEW_UA_MARKER (drift-guarded by
# tests/dashboard/test_native_chrome.py).
_WEBVIEW_UA_MARKER = "QuodeqDesktop"

# Host header must look like a bare hostname/IPv4 or a bracketed IPv6
# literal (RFC 3986 host syntax, e.g. "[::1]:4180"), with an optional port,
# before it's trusted enough to interpolate into the CSP connect-src
# directive. Rejects quotes, whitespace, and other characters that could
# inject extra CSP directives or sources via a spoofed Host header.
# The IPv6 branch matters here: ::1 is a first-class local address elsewhere
# in this app (_LOCALHOST_ADDRS below, dashboard/_networking.py,
# dashboard/_webview_window_native_ops.py's reload allowlist), so a client
# reaching this dashboard over IPv6 loopback is a real access path, not a
# hypothetical.
_VALID_HOST_RE = re.compile(r"^(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])(:\d+)?$")


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
    if hasattr(store, "check_and_record"):
        limited = store.check_and_record(ip, now)
    else:
        # Back-compat: external RateLimitStore implementers written against
        # the old check()/record() Protocol don't have check_and_record.
        limited = store.check(ip, now)
        if not limited:
            store.record(ip, now)
    if limited:
        return jsonify({"error": "Too many requests", "code": "RATE_LIMITED"}), HTTPStatus.TOO_MANY_REQUESTS
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
            f"http://127.0.0.1:{p} http://localhost:{p} "
            f"ws://127.0.0.1:{p} ws://localhost:{p}"
            for p in (4180, 4181, 4182, 4183)
        )
        # The primary bind port isn't known here; add same-origin ws explicitly.
        _self_ws = ""
        try:
            from flask import request as _req
            _self_ws = _same_origin_ws_sources(_req.host)
        except Exception:
            _self_ws = ""
        is_webview = _WEBVIEW_UA_MARKER in request.headers.get("User-Agent", "")
        script_src = "script-src 'self' 'unsafe-eval'" if is_webview else "script-src 'self'"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"connect-src 'self' {_alt_port_origins} {_self_ws}; "
            f"{script_src}; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "mask-src 'self' data:; "
            "frame-ancestors 'none'"
        )
        return response
