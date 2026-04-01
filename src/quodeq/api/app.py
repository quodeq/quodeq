"""Flask REST API for project reports, evaluations, and tooling discovery."""

from __future__ import annotations

import hmac
import logging
import os
import sys
import time
from http import HTTPStatus

_logger = logging.getLogger(__name__)

from flask import Flask, Response, jsonify, request

from quodeq.api._rate_limit import (
    InMemoryRateLimitStore,
    RateLimitStore,
    create_rate_limit_store,
)
from quodeq.provider.base import ActionProvider
from quodeq.shared.utils import get_action_api_host, get_action_api_port, get_static_dist

from quodeq.api.routes import (
    register_project_list_routes,
    register_project_data_routes,
    register_evaluation_list_routes,
    register_evaluation_item_routes,
    register_discovery_routes,
    register_static_routes,
)
from quodeq.api.standards_routes import register_standards_routes
from quodeq.api.routes_findings import register_findings_routes

_HEALTH_PATH = "/api/health"
_RATE_LIMITED_GET_PATHS = frozenset({"/api/browse"})
_EVALUATION_RATE_LIMIT_WINDOW = 300  # 5-minute window for evaluation creation
_EVALUATION_RATE_LIMIT_MAX = 10  # max evaluations per window


def _default_provider() -> ActionProvider:
    """Create the default filesystem-based provider (lazy import)."""
    from quodeq.provider.filesystem import FilesystemActionProvider
    return FilesystemActionProvider()


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
    ip = request.remote_addr or "unknown"
    now = time.monotonic()
    if store.check(ip, now):
        return jsonify({"error": "Too many requests", "code": "RATE_LIMITED"}), HTTPStatus.TOO_MANY_REQUESTS
    store.record(ip, now)
    return None


def _configure_security(app: Flask, rate_limit_store: RateLimitStore, api_key: str | None) -> None:
    """Register before/after request hooks for auth, CSRF, rate-limiting, and security headers."""

    @app.before_request
    def _audit_log() -> None:
        actor = ""
        if api_key:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer ") and len(auth) > 11:
                actor = f", actor=key:***{auth[-4:]}"
        _logger.info("API: %s %s (remote_addr=%s%s)", request.method, request.path, request.remote_addr, actor)

    @app.before_request
    def _security_checks() -> Response | tuple[Response, int] | None:
        return _check_auth(api_key) or _check_csrf() or _check_rate_limit(rate_limit_store)

    @app.after_request
    def _add_security_headers(response: Response) -> Response:
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response


def create_app(
    provider: ActionProvider | None = None,
    static_dist: str | None = None,
    rate_limit_store: RateLimitStore | None = None,
    api_key: str | None = None,
    test_config: dict | None = None,
) -> Flask:
    """Create and configure the Flask application with all API routes."""
    app = Flask(__name__)
    if test_config is not None:
        app.config.update(test_config)
    provider = provider or _default_provider()
    store = rate_limit_store or create_rate_limit_store()
    eval_store = InMemoryRateLimitStore(
        window=_EVALUATION_RATE_LIMIT_WINDOW, max_requests=_EVALUATION_RATE_LIMIT_MAX,
    )
    if "STANDARDS_EVALUATORS_DIR" not in app.config:
        from quodeq.config.paths import default_paths
        paths = default_paths()
        app.config["STANDARDS_EVALUATORS_DIR"] = str(paths.evaluators_dir)
        app.config["STANDARDS_COMPILED_DIR"] = str(paths.standards_dir / "compiled")
        app.config["STANDARDS_DIMENSIONS_FILE"] = str(paths.dimensions_file)

    if api_key is None:
        _logger.warning(
            "QUODEQ_API_KEY is not set — API restricted to localhost only. "
            "Set QUODEQ_API_KEY to enable authenticated remote access."
        )

    _configure_security(app, store, api_key)

    @app.get("/api/health")
    def health() -> Response:
        """Return a simple health-check response."""
        from quodeq import __version__
        return jsonify({"ok": True, "version": __version__})

    _register_all_routes(app, provider, eval_store, static_dist)
    return app


def _register_all_routes(
    app: Flask, provider: ActionProvider,
    eval_store: RateLimitStore, static_dist: str | None,
) -> None:
    """Register all API route groups on the app."""
    register_project_list_routes(app, provider)
    register_project_data_routes(app, provider)
    register_evaluation_list_routes(app, provider, eval_store)
    register_evaluation_item_routes(app, provider)
    register_discovery_routes(app, provider)
    register_standards_routes(app)
    register_findings_routes(app)
    register_static_routes(app, static_dist)


def main(env: dict[str, str] | None = None) -> None:
    """Start the Flask development server using environment configuration."""
    import signal

    _env = env if env is not None else os.environ
    # SECURITY: API key read from environment. For hardened deployments,
    # consider a secrets manager or platform keychain instead.
    app = create_app(static_dist=get_static_dist(), api_key=_env.get("QUODEQ_API_KEY"))

    def _handle_shutdown(signum: int, frame: object) -> None:
        raise SystemExit(0)

    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    app.run(host=get_action_api_host(), port=get_action_api_port(), debug=False)


if __name__ == "__main__":
    main()
