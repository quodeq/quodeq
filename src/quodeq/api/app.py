"""Flask REST API for project reports, evaluations, and tooling discovery."""

from __future__ import annotations

import logging
import os
import sys

from flask import Flask, Response, jsonify

from quodeq.api._rate_limit import (
    InMemoryRateLimitStore,
    RateLimitStore,
    create_rate_limit_store,
)
from quodeq.api.routes_registry import register_all_routes
from quodeq.api.security import configure_security
from quodeq.services.base import ActionProvider
from quodeq.shared.utils import get_action_api_host, get_action_api_port, get_static_dist

_logger = logging.getLogger(__name__)

_EVALUATION_RATE_LIMIT_WINDOW = 300  # 5-minute window for evaluation creation
_EVALUATION_RATE_LIMIT_MAX = 10  # max evaluations per window


def _default_provider() -> ActionProvider:
    """Create the default filesystem-based provider (lazy import)."""
    from quodeq.services.filesystem import FilesystemActionProvider
    return FilesystemActionProvider()


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

    configure_security(app, store, api_key)

    @app.get("/api/health")
    def health() -> Response:
        """Return a simple health-check response with server info."""
        from quodeq import __version__
        from quodeq.shared.utils import get_action_api_host, get_action_api_port
        host = get_action_api_host()
        port = get_action_api_port()
        display_host = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
        return jsonify({
            "ok": True,
            "version": __version__,
            "host": host,
            "port": port,
            "address": f"{display_host}:{port}",
            "pid": os.getpid(),
        })

    register_all_routes(app, provider, eval_store, static_dist)
    return app


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
