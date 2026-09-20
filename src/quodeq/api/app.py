"""Flask REST API for project reports, evaluations, and tooling discovery."""

from __future__ import annotations

import logging
import os
import signal
from collections.abc import Mapping

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
from quodeq.shared._env import env_int
from quodeq.shared._env_inject import resolve_env
from quodeq.shared.utils import get_action_api_host, get_action_api_port, get_static_dist

_logger = logging.getLogger(__name__)

_DEFAULT_EVALUATION_RATE_LIMIT_WINDOW = 300
_DEFAULT_EVALUATION_RATE_LIMIT_MAX = 10


def _default_provider() -> ActionProvider:
    """Create the default filesystem-based provider (lazy import)."""
    from pathlib import Path
    from quodeq.services.filesystem import FilesystemActionProvider
    from quodeq.shared._env import get_index_db_path
    return FilesystemActionProvider(index_db_path=Path(get_index_db_path()))


def _configure_logging(
    app: Flask, env: Mapping[str, str] | None = None,
) -> tuple[LogBuffer, bool]:
    """Set up log buffer and request logging. Returns (log_buffer, verbose).

    *env* overrides the ``QUODEQ_VERBOSE`` lookup and defaults to ``os.environ``.
    """
    log_buffer = LogBuffer()
    app.extensions["log_buffer"] = log_buffer

    verbose = resolve_env(env).get("QUODEQ_VERBOSE") == "1"
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


def _configure_upload_limits(app: Flask) -> None:
    """Cap multipart uploads (project import) at the same size as the export
    limit, plus a small headroom for multipart framing. Flask aborts with
    413 before reading the full body, which keeps large bogus uploads cheap.
    """
    from quodeq.api.zip import _max_zip_size_bytes
    app.config.setdefault("MAX_CONTENT_LENGTH", _max_zip_size_bytes() + 1 * 1024 * 1024)


def _configure_extensions(app: Flask) -> None:
    """Set up per-app extensions: assistant turn/SSE registry, background
    task runner, and the CWE lookup cache."""
    # Per-app assistant turn/SSE registry (composition root for the state the
    # assistant routes used to keep in module globals).
    from quodeq.api.assistant_routes import AssistantTurnState
    app.extensions["assistant_turns"] = AssistantTurnState()

    from quodeq.services.background import ThreadBackgroundRunner
    from quodeq.shared.log_sink import SHARED_LOG
    app.extensions["background"] = ThreadBackgroundRunner(log=SHARED_LOG)

    from quodeq.api.standards_read_routes import CweCache
    app.extensions["cwe_cache"] = CweCache()


def _configure_paths_and_cleanup(app: Flask, env: dict[str, str] | None = None) -> None:
    """Sweep orphaned ephemeral clones, and default the STANDARDS_*/
    ASSISTANT_DB_PATH config entries when the caller hasn't set them.

    *env* overrides the path lookups and defaults to ``os.environ``."""
    from pathlib import Path
    from quodeq.services._ephemeral_cleanup import sweep_orphaned_clones
    from quodeq.shared._env import get_clones_dir, get_evaluations_dir, get_quodeq_dir

    try:
        sweep_orphaned_clones(get_clones_dir(env), Path(get_evaluations_dir(env=env)))
    except Exception as exc:  # pragma: no cover - best-effort cleanup
        _logger.warning("Orphaned-clone sweep failed at startup: %s", exc)

    if "STANDARDS_EVALUATORS_DIR" not in app.config:
        paths = default_paths()
        app.config["STANDARDS_EVALUATORS_DIR"] = str(paths.evaluators_dir)
        app.config["STANDARDS_COMPILED_DIR"] = str(paths.standards_dir / "compiled")
        app.config["STANDARDS_DIMENSIONS_FILE"] = str(paths.dimensions_file)

    if "ASSISTANT_DB_PATH" not in app.config:
        # QUODEQ_DIR must redirect this like every other state path, else
        # env-isolated servers write sessions into the real ~/.quodeq store.
        app.config["ASSISTANT_DB_PATH"] = str(get_quodeq_dir(env) / "assistant.db")


def _configure_app(
    app: Flask,
    provider: ActionProvider,
    test_config: dict | None,
    env: dict[str, str] | None = None,
) -> None:
    """Apply the caller's config overrides, then the app-level defaults and
    extensions that every route depends on."""
    if test_config is not None:
        app.config.update(test_config)
    _configure_upload_limits(app)
    app.config["_provider"] = provider
    _configure_extensions(app)
    _configure_paths_and_cleanup(app, env)


def _build_rate_limit_store(
    rate_limit_store: RateLimitStore | None = None,
    env: dict[str, str] | None = None,
) -> tuple[RateLimitStore, RateLimitStore]:
    """Return the (API, evaluation) rate-limit stores.

    The API limiter honours a caller-supplied shared backend; the evaluation
    limiter is always process-local with its own window and cap, read here at
    call time rather than at import. *env* overrides both lookups for tests
    and defaults to ``os.environ``.
    """
    store = rate_limit_store or create_rate_limit_store(env=env)
    eval_store = InMemoryRateLimitStore(
        window=env_int("QUODEQ_RATE_LIMIT_WINDOW", _DEFAULT_EVALUATION_RATE_LIMIT_WINDOW, env=env),
        max_requests=env_int("QUODEQ_RATE_LIMIT_MAX", _DEFAULT_EVALUATION_RATE_LIMIT_MAX, env=env),
    )
    return store, eval_store


def _configure_request_handling(
    app: Flask,
    store: RateLimitStore,
    api_key: str | None,
    env: dict[str, str] | None = None,
) -> LogBuffer:
    """Install the per-request layers (auth, compression, logging) and the
    health endpoint. Returns the log buffer the routes stream from."""
    if api_key is None:
        _logger.warning(
            "QUODEQ_API_KEY is not set — API restricted to localhost only. "
            "Set QUODEQ_API_KEY to enable authenticated remote access."
        )

    configure_security(app, store, api_key, env)
    from quodeq.api._compression import configure_compression
    configure_compression(app)
    app.config["QUODEQ_API_KEY"] = api_key
    from quodeq.shared.utils import get_action_api_host as _gah
    app.config["QUODEQ_BIND_HOST"] = _gah(env)
    log_buffer, verbose = _configure_logging(app, env)
    _register_health_route(app, verbose)
    return log_buffer


def create_app(
    provider: ActionProvider | None = None,
    static_dist: str | None = None,
    rate_limit_store: RateLimitStore | None = None,
    api_key: str | None = None,
    test_config: dict | None = None,
    env: dict[str, str] | None = None,
) -> Flask:
    """Create and configure the Flask application with all API routes.

    *env* is the composition root for every environment read the
    configuration and route-registration steps do: it is resolved here, at
    app-creation time, and handed to them instead of each one reaching for
    ``os.environ``. ``None`` keeps the process environment.

    It does not cover the SSE/tail tuning variables — ``QUODEQ_SSE_TICK_MS``,
    ``QUODEQ_SSE_FINDINGS_BATCH``, ``QUODEQ_LOG_STREAM_POLL_MS``,
    ``QUODEQ_LOG_STREAM_MAX_WAIT_S``, ``QUODEQ_LOG_TAIL_MAX_BYTES`` — which
    stay process-scoped and are read per request inside the stream
    generators, so a test can still set one mid-run.
    """
    app = Flask(__name__)
    provider = provider or _default_provider()
    _configure_app(app, provider, test_config, env)
    store, eval_store = _build_rate_limit_store(rate_limit_store, env)
    log_buffer = _configure_request_handling(app, store, api_key, env)
    register_all_routes(app, provider, eval_store, static_dist, log_buffer, env)
    return app


def main(env: dict[str, str] | None = None) -> None:
    """Start the Flask development server using environment configuration."""
    from quodeq.shared._io import configure_stdio_utf8
    configure_stdio_utf8()
    _env = resolve_env(env)
    # SECURITY: API key read from environment. For hardened deployments,
    # consider a secrets manager or platform keychain instead.
    app = create_app(
        static_dist=get_static_dist(env),
        api_key=_env.get("QUODEQ_API_KEY"),
        env=env,
    )

    # Evaluation subprocesses are spawned with start_new_session=True so they
    # survive the API process dying. Intentionally do NOT kill them on API
    # shutdown — otherwise launching a second dashboard (which calls
    # _kill_stale_action_api on the first) would cascade and kill any scan in
    # flight. Scans have their own lifecycle; use the UI cancel button or the
    # DELETE endpoint for explicit stops.
    def _handle_shutdown(_signum: int, _frame: object) -> None:
        raise SystemExit(0)

    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    # Warm the score caches in the background so the first requests after an
    # upgrade hit warm or warming caches instead of recomputing inline. Also
    # migrate and index the result cache once, off the request path, so
    # estimates stop undercounting cached files after an upgrade.
    # main() only: create_app callers (tests, embedding) stay thread-free.
    try:
        from quodeq.api.routes_common import reports_dir  # noqa: PLC0415
        from quodeq.services._warmup import engine as warmup_engine  # noqa: PLC0415
        from quodeq.services.cache_maintenance import start_cache_maintenance  # noqa: PLC0415
        from quodeq.shared.log_sink import SHARED_LOG  # noqa: PLC0415
        warmup_engine.start(reports_dir())
        start_cache_maintenance(log=SHARED_LOG)
    except Exception:  # pragma: no cover - warm-up must never block serving
        logging.getLogger(__name__).warning("warm-up start failed", exc_info=True)

    app.run(host=get_action_api_host(env), port=get_action_api_port(env), debug=False)


if __name__ == "__main__":
    main()
