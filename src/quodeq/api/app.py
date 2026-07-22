"""Flask REST API for project reports, evaluations, and tooling discovery."""

from __future__ import annotations

import logging
import os
import signal
import sys

from flask import Flask, Response, jsonify

from quodeq.api._log_buffer import LogBuffer
from quodeq.api._rate_limit import (
    InMemoryRateLimitStore,
    RateLimitStore,
    create_rate_limit_store,
)
from quodeq import __version__
from quodeq.api.routes_registry import register_all_routes
from quodeq.api.security import configure_security
from quodeq.config.paths import default_paths
from quodeq.services.base import ActionProvider
from quodeq.shared.utils import get_action_api_host, get_action_api_port, get_static_dist

_logger = logging.getLogger(__name__)

_EVALUATION_RATE_LIMIT_WINDOW = int(os.environ.get("QUODEQ_RATE_LIMIT_WINDOW", "300"))
_EVALUATION_RATE_LIMIT_MAX = int(os.environ.get("QUODEQ_RATE_LIMIT_MAX", "10"))


def _default_provider() -> ActionProvider:
    """Create the default filesystem-based provider (lazy import)."""
    from pathlib import Path
    from quodeq.services.filesystem import FilesystemActionProvider
    from quodeq.shared._env import get_index_db_path
    return FilesystemActionProvider(index_db_path=Path(get_index_db_path()))


def _configure_logging(app: Flask) -> tuple[LogBuffer, bool]:
    """Set up log buffer and request logging. Returns (log_buffer, verbose)."""
    log_buffer = LogBuffer()
    app.extensions["log_buffer"] = log_buffer

    verbose = os.environ.get("QUODEQ_VERBOSE") == "1"
    for name in ("werkzeug", "quodeq.api"):
        lgr = logging.getLogger(name)
        lgr.handlers = [log_buffer.handler]
        if verbose:
            lgr.handlers.append(logging.StreamHandler())
        lgr.propagate = False
    return log_buffer, verbose


def _register_health_route(app: Flask, verbose: bool) -> None:
    """Register the /api/health endpoint."""
    @app.get("/api/health")
    def health() -> Response:
        """Return a simple health-check response with server info."""
        host = get_action_api_host()
        port = get_action_api_port()
        display_host = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
        payload: dict[str, object] = {
            "ok": True,
            "version": __version__,
            "host": host,
            "port": port,
            "address": f"{display_host}:{port}",
        }
        if verbose:
            payload["pid"] = os.getpid()
        return jsonify(payload)


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
    # Cap multipart uploads (project import) at the same size as the export
    # limit, plus a small headroom for multipart framing. Flask aborts with
    # 413 before reading the full body, which keeps large bogus uploads cheap.
    from quodeq.api.zip import _max_zip_size_bytes
    app.config.setdefault("MAX_CONTENT_LENGTH", _max_zip_size_bytes() + 1 * 1024 * 1024)
    provider = provider or _default_provider()
    app.config["_provider"] = provider

    from pathlib import Path
    from quodeq.services._ephemeral_cleanup import sweep_orphaned_clones
    from quodeq.shared._env import get_clones_dir, get_evaluations_dir, get_quodeq_dir

    try:
        sweep_orphaned_clones(get_clones_dir(), Path(get_evaluations_dir()))
    except Exception as exc:  # pragma: no cover - best-effort cleanup
        _logger.warning("Orphaned-clone sweep failed at startup: %s", exc)

    store = rate_limit_store or create_rate_limit_store()
    eval_store = InMemoryRateLimitStore(
        window=_EVALUATION_RATE_LIMIT_WINDOW, max_requests=_EVALUATION_RATE_LIMIT_MAX,
    )
    if "STANDARDS_EVALUATORS_DIR" not in app.config:
        paths = default_paths()
        app.config["STANDARDS_EVALUATORS_DIR"] = str(paths.evaluators_dir)
        app.config["STANDARDS_COMPILED_DIR"] = str(paths.standards_dir / "compiled")
        app.config["STANDARDS_DIMENSIONS_FILE"] = str(paths.dimensions_file)

    if "ASSISTANT_DB_PATH" not in app.config:
        # QUODEQ_DIR must redirect this like every other state path, else
        # env-isolated servers write sessions into the real ~/.quodeq store.
        app.config["ASSISTANT_DB_PATH"] = str(get_quodeq_dir() / "assistant.db")

    if api_key is None:
        _logger.warning(
            "QUODEQ_API_KEY is not set — API restricted to localhost only. "
            "Set QUODEQ_API_KEY to enable authenticated remote access."
        )

    configure_security(app, store, api_key)
    from quodeq.api._compression import configure_compression
    configure_compression(app)
    app.config["QUODEQ_API_KEY"] = api_key
    from quodeq.shared.utils import get_action_api_host as _gah
    app.config["QUODEQ_BIND_HOST"] = _gah()
    log_buffer, verbose = _configure_logging(app)
    _register_health_route(app, verbose)
    register_all_routes(app, provider, eval_store, static_dist, log_buffer)
    return app


def main(env: dict[str, str] | None = None) -> None:
    """Start the Flask development server using environment configuration."""
    from quodeq.shared._io import configure_stdio_utf8
    configure_stdio_utf8()
    _env = env if env is not None else os.environ
    # SECURITY: API key read from environment. For hardened deployments,
    # consider a secrets manager or platform keychain instead.
    app = create_app(static_dist=get_static_dist(), api_key=_env.get("QUODEQ_API_KEY"))

    # Evaluation subprocesses are spawned with start_new_session=True so they
    # survive the API process dying. Intentionally do NOT kill them on API
    # shutdown — otherwise launching a second dashboard (which calls
    # _kill_stale_action_api on the first) would cascade and kill any scan in
    # flight. Scans have their own lifecycle; use the UI cancel button or the
    # DELETE endpoint for explicit stops.
    def _handle_shutdown(signum: int, frame: object) -> None:
        raise SystemExit(0)

    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    app.run(host=get_action_api_host(), port=get_action_api_port(), debug=False)


if __name__ == "__main__":
    main()
