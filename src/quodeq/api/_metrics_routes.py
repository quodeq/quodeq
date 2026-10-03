"""Runtime metrics: ``Server-Timing`` on every response and ``/api/debug/metrics``.

The header answers "what did this request cost" from the browser's network
panel; the endpoint answers "what is the process holding" for the operator
on the same machine. Both read the request-scoped counters in
``quodeq.shared.request_metrics`` and the ``StampCache`` registry; nothing
here patches the interpreter.
"""
from __future__ import annotations

import os
import sys
import threading
from http import HTTPStatus

try:
    import resource
except ImportError:  # Windows has no ``resource`` module.
    resource = None

from flask import Flask, Response, g, jsonify, request

from quodeq.api.helpers import json_error
from quodeq.api.routes_common import is_local_request
from quodeq.shared import request_metrics
from quodeq.shared.request_metrics import RequestRates
from quodeq.shared.stamp_memo import CACHES

_TOKEN_KEY = "_request_metrics_token"
_EXT_KEY = "request_rates"
# macOS reports ru_maxrss in bytes, Linux in kilobytes.
_RSS_UNIT = 1 if sys.platform == "darwin" else 1024


def configure_request_metrics(app: Flask) -> None:
    """Open a metrics scope per request and emit ``Server-Timing`` on the way out."""
    rates = RequestRates()
    app.extensions[_EXT_KEY] = rates

    @app.before_request
    def _open_scope() -> None:
        setattr(g, _TOKEN_KEY, request_metrics.begin())

    @app.after_request
    def _emit_server_timing(response: Response) -> Response:
        metrics = request_metrics.current()
        if metrics is not None:
            response.headers["Server-Timing"] = request_metrics.server_timing(metrics)
        rates.record(request.url_rule.rule if request.url_rule else request.path)
        return response

    @app.teardown_request
    def _close_scope(_exc: BaseException | None) -> None:
        token = g.pop(_TOKEN_KEY, None)
        if token is not None:
            request_metrics.end(token)


def _process_stats() -> dict[str, object]:
    times = os.times()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * _RSS_UNIT if resource else None
    return {
        "pid": os.getpid(),
        "rss_bytes": rss,
        "cpu_user_s": round(times.user, 3),
        "cpu_system_s": round(times.system, 3),
        "threads": threading.active_count(),
    }


def metrics_payload(app: Flask) -> dict[str, object]:
    """The ``/api/debug/metrics`` body: process, caches, request rates."""
    caches = sorted((cache.stats() for cache in list(CACHES)), key=lambda c: str(c["name"]))
    rates: RequestRates | None = app.extensions.get(_EXT_KEY)
    return {
        "process": _process_stats(),
        "caches": caches,
        "requests_last_minute": rates.snapshot() if rates else {},
    }


def register_metrics_routes(app: Flask) -> None:
    """Install the per-request hooks and ``GET /api/debug/metrics`` (loopback callers only).

    The hooks are registered here rather than with the other response layers
    so the runtime-metrics feature lives in one module.
    """
    configure_request_metrics(app)

    @app.get("/api/debug/metrics")
    def debug_metrics() -> Response | tuple[Response, int]:
        if not is_local_request():
            return json_error("metrics are local-only", HTTPStatus.FORBIDDEN, "FORBIDDEN")
        return jsonify(metrics_payload(app))
