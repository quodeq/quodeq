"""Flask REST API for project reports, evaluations, and tooling discovery."""

from __future__ import annotations

import hmac
import logging
import os
import sys
import time
from collections import OrderedDict
from http import HTTPStatus
from typing import Protocol, runtime_checkable

_logger = logging.getLogger(__name__)

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

_HEALTH_PATH = "/api/health"

_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 60  # max state-changing requests per window
_RATE_STORE_MAX_IPS = 10_000  # max tracked IPs to prevent unbounded memory growth


@runtime_checkable
class RateLimitStore(Protocol):
    """Abstraction for rate-limit state storage.

    Implementations track per-IP request timestamps within a sliding window.
    The default ``InMemoryRateLimitStore`` keeps state in-process; replace with
    a Redis-backed implementation for multi-worker deployments.
    """

    def record(self, ip: str, now: float) -> None:
        """Record a state-changing request from *ip* at time *now*."""
        ...

    def check(self, ip: str, now: float) -> bool:
        """Return True if *ip* has exceeded the rate limit at time *now*."""
        ...


class InMemoryRateLimitStore:
    """Process-local rate-limit store backed by an LRU OrderedDict.

    For multi-worker deployments, implement the ``RateLimitStore`` protocol
    with a shared backend (e.g. Redis) and pass it to ``create_app`` via
    the ``rate_limit_store`` parameter, or register a factory via
    ``create_rate_limit_store``.
    """

    def __init__(
        self,
        window: float = _RATE_LIMIT_WINDOW,
        max_requests: int = _RATE_LIMIT_MAX,
        max_ips: int = _RATE_STORE_MAX_IPS,
    ) -> None:
        self._store: OrderedDict[str, list[float]] = OrderedDict()
        self._window = window
        self._max_requests = max_requests
        self._max_ips = max_ips

    def _evict_stale(self, now: float) -> None:
        if len(self._store) <= self._max_ips:
            return
        stale = []
        for k, v in self._store.items():
            if all(now - t >= self._window for t in v):
                stale.append(k)
            else:
                break  # LRU order: first non-stale entry means the rest are newer
        for k in stale:
            del self._store[k]
        if len(self._store) > self._max_ips:
            self._store.clear()

    def record(self, ip: str, now: float) -> None:
        """Record a state-changing request from *ip* at time *now*."""
        self._store.setdefault(ip, []).append(now)
        self._store.move_to_end(ip)

    def check(self, ip: str, now: float) -> bool:
        """Return True if *ip* has exceeded the rate limit at time *now*."""
        self._evict_stale(now)
        timestamps = [t for t in self._store.get(ip, []) if now - t < self._window]
        if not timestamps:
            self._store.pop(ip, None)
        else:
            self._store[ip] = timestamps
            self._store.move_to_end(ip)
        return len(timestamps) >= self._max_requests


def create_rate_limit_store() -> RateLimitStore:
    """Create the default rate-limit store.

    Override this factory to plug in a shared backend for multi-worker
    deployments (e.g. Redis).  The returned object must satisfy the
    ``RateLimitStore`` protocol.
    """
    return InMemoryRateLimitStore()


def _default_provider() -> ActionProvider:
    """Create the default filesystem-based provider (lazy import)."""
    from quodeq.provider.filesystem import FilesystemActionProvider
    return FilesystemActionProvider()


def _check_auth(api_key: str | None) -> Response | tuple[Response, int] | None:
    """Verify API key authentication when *api_key* is set."""
    if request.path == _HEALTH_PATH:
        return None
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
    if not origin:
        return jsonify({"error": "Origin header required", "code": "FORBIDDEN"}), HTTPStatus.FORBIDDEN
    allowed = {f"http://{request.host}", f"https://{request.host}"}
    if origin not in allowed:
        return jsonify({"error": "Origin not allowed", "code": "FORBIDDEN"}), HTTPStatus.FORBIDDEN
    return None


def _check_rate_limit(store: RateLimitStore) -> Response | tuple[Response, int] | None:
    """Enforce rate limiting on state-changing requests."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    ip = request.remote_addr or "unknown"
    now = time.monotonic()
    if store.check(ip, now):
        return jsonify({"error": "Too many requests", "code": "RATE_LIMITED"}), HTTPStatus.TOO_MANY_REQUESTS
    store.record(ip, now)
    return None


def create_app(
    provider: ActionProvider | None = None,
    static_dist: str | None = None,
    rate_limit_store: RateLimitStore | None = None,
    api_key: str | None = None,
) -> Flask:
    """Create and configure the Flask application with all API routes.

    *api_key* overrides the ``QUODEQ_API_KEY`` env-var lookup when provided,
    making the app testable without environment mutation.  Pass an empty string
    to explicitly disable authentication.
    """
    app = Flask(__name__)
    provider = provider or _default_provider()
    store = rate_limit_store or create_rate_limit_store()
    if api_key is None:
        _msg = (
            "QUODEQ_API_KEY is not set — API endpoints are unauthenticated. "
            "Set QUODEQ_API_KEY for production use."
        )
        _logger.warning(_msg)

    @app.before_request
    def _security_checks() -> Response | tuple[Response, int] | None:
        return _check_auth(api_key) or _check_csrf() or _check_rate_limit(store)

    @app.after_request
    def _add_security_headers(response: Response) -> Response:
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    @app.get("/api/health")
    def health() -> Response:
        """Return a simple health-check response."""
        from quodeq import __version__
        return jsonify({"ok": True, "version": __version__})

    register_project_list_routes(app, provider)
    register_project_data_routes(app, provider)
    register_evaluation_list_routes(app, provider)
    register_evaluation_item_routes(app, provider)
    register_discovery_routes(app, provider)
    register_static_routes(app, static_dist)
    return app


def main() -> None:
    """Start the Flask development server using environment configuration."""
    import signal

    app = create_app(static_dist=get_static_dist(), api_key=os.environ.get("QUODEQ_API_KEY"))

    def _handle_shutdown(signum: int, frame: object) -> None:
        raise SystemExit(0)

    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    app.run(host=get_action_api_host(), port=get_action_api_port(), debug=False)


if __name__ == "__main__":
    main()
