"""Flask REST API for project reports, evaluations, and tooling discovery."""

from __future__ import annotations

import hmac
import os
import time
from collections import OrderedDict
from http import HTTPStatus

from flask import Flask, Response, jsonify, request

from quodeq.provider.base import ActionProvider
from quodeq.shared.utils import get_action_api_host, get_action_api_port, get_static_dist

from quodeq.action_api_routes import (
    register_project_list_routes,
    register_project_data_routes,
    register_evaluation_list_routes,
    register_evaluation_item_routes,
    register_discovery_routes,
    register_static_routes,
)

_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 60  # max state-changing requests per window
_RATE_STORE_MAX_IPS = 10_000  # max tracked IPs to prevent unbounded memory growth


def _default_provider() -> ActionProvider:
    """Create the default filesystem-based provider (lazy import)."""
    from quodeq.provider.filesystem import FilesystemActionProvider
    return FilesystemActionProvider()


def _check_auth() -> Response | tuple[Response, int] | None:
    """Verify API key authentication when QUODEQ_API_KEY is set."""
    if request.path == "/api/health":
        return None
    api_key = os.environ.get("QUODEQ_API_KEY")
    if api_key:
        auth = request.headers.get("Authorization", "")
        if not hmac.compare_digest(auth, f"Bearer {api_key}"):
            return jsonify({"error": "Unauthorized", "code": "UNAUTHORIZED"}), HTTPStatus.UNAUTHORIZED
    return None


def _check_csrf() -> Response | tuple[Response, int] | None:
    """Verify Origin header on state-changing requests."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    origin = request.headers.get("Origin")
    if origin:
        allowed = {f"http://{request.host}", f"https://{request.host}"}
        if origin not in allowed:
            return jsonify({"error": "Origin not allowed", "code": "FORBIDDEN"}), HTTPStatus.FORBIDDEN
    return None


def _check_rate_limit(rate_store: OrderedDict) -> Response | tuple[Response, int] | None:
    """Enforce rate limiting on state-changing requests.

    rate_store is an LRU-ordered OrderedDict (most-recently-used at the end),
    which lets the stale-IP scan stop at the first non-stale entry instead of
    scanning all 10,000 tracked IPs on every state-changing request.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    ip = request.remote_addr or "unknown"
    now = time.monotonic()
    if len(rate_store) > _RATE_STORE_MAX_IPS:
        stale = []
        for k, v in rate_store.items():
            if all(now - t >= _RATE_LIMIT_WINDOW for t in v):
                stale.append(k)
            else:
                break  # LRU order: first non-stale entry means the rest are newer
        for k in stale:
            del rate_store[k]
        if len(rate_store) > _RATE_STORE_MAX_IPS:
            rate_store.clear()
    timestamps = [t for t in rate_store.get(ip, []) if now - t < _RATE_LIMIT_WINDOW]
    if not timestamps:
        rate_store.pop(ip, None)
    else:
        rate_store[ip] = timestamps
        rate_store.move_to_end(ip)
    if len(timestamps) >= _RATE_LIMIT_MAX:
        return jsonify({"error": "Too many requests", "code": "RATE_LIMITED"}), HTTPStatus.TOO_MANY_REQUESTS
    rate_store.setdefault(ip, []).append(now)
    rate_store.move_to_end(ip)
    return None


def create_app(provider: ActionProvider | None = None, static_dist: str | None = None) -> Flask:
    """Create and configure the Flask application with all API routes."""
    app = Flask(__name__)
    provider = provider or _default_provider()
    rate_store: OrderedDict[str, list[float]] = OrderedDict()

    @app.before_request
    def _security_checks() -> Response | tuple[Response, int] | None:
        return _check_auth() or _check_csrf() or _check_rate_limit(rate_store)

    @app.after_request
    def _add_security_headers(response: Response) -> Response:
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    @app.get("/api/health")
    def health() -> Response:
        """Return a simple health-check response."""
        try:
            from importlib.metadata import version as _pkg_version
            v = _pkg_version("quodeq")
        except Exception:
            v = None
        return jsonify({"ok": True, "version": v})

    register_project_list_routes(app, provider)
    register_project_data_routes(app, provider)
    register_evaluation_list_routes(app, provider)
    register_evaluation_item_routes(app, provider)
    register_discovery_routes(app, provider)
    register_static_routes(app, static_dist)
    return app


def main() -> None:
    """Start the Flask development server using environment configuration."""
    app = create_app(static_dist=get_static_dist())
    app.run(host=get_action_api_host(), port=get_action_api_port())


if __name__ == "__main__":
    main()
