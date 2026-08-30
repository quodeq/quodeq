"""GET routes for the Standards Browser & Editor."""
from __future__ import annotations

import logging
import os
import threading
import time as _time
from typing import Callable

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.core.types import to_camel_dict

logger = logging.getLogger(__name__)


class CweCache:
    """TTL-bounded cache for the (rarely-changing) CWE reference list.

    One instance per Flask app (``app.extensions["cwe_cache"]``, created in
    ``create_app``) so two apps in one process -- or two tests -- never
    share cache state. Double-checked locking: the fast path (cache warm)
    never blocks on the lock; only an expired cache pays the lock cost, and
    only ONE reload runs even when multiple threads race at expiry.
    """

    def __init__(
        self, ttl_s: int | None = None, clock: Callable[[], float] = _time.monotonic,
    ) -> None:
        # Read PER INSTANCE (not at import time) so tests can construct a
        # fresh CweCache after changing QUODEQ_CWE_CACHE_TTL, and so two
        # instances in the same process can disagree.
        self._ttl_s = ttl_s if ttl_s is not None else int(os.environ.get("QUODEQ_CWE_CACHE_TTL", "3600"))
        self._clock = clock
        self._cache: list | None = None
        self._cache_time: float = 0.0
        self._lock = threading.Lock()

    def get(self, loader: Callable[[], list]) -> list:
        """Return the CWE list, reloading at most once when the cache has expired."""
        now = self._clock()
        # Fast path: cache is valid — no lock needed.
        if self._cache is not None and (now - self._cache_time) <= self._ttl_s:
            return self._cache
        # Slow path: acquire the lock, then re-check inside it.
        with self._lock:
            now = self._clock()  # re-read after acquiring
            if self._cache is None or (now - self._cache_time) > self._ttl_s:
                self._cache = loader()
                self._cache_time = now
            return self._cache

    def clear(self) -> None:
        self._cache = None
        self._cache_time = 0.0


def _cache(app: Flask) -> CweCache:
    """The app's CWE cache. ``create_app`` instantiates it; setdefault keeps
    bare test apps (register_read_routes on a plain Flask) working."""
    return app.extensions.setdefault("cwe_cache", CweCache())


def register_read_routes(app: Flask, get_service, get_library_client) -> None:
    """Register GET routes for the standards API.

    Args:
        app: The Flask application instance.
        get_service: Factory callable returning the standards service.
        get_library_client: Factory callable returning the library client (or None).
    """

    @app.get("/api/standards/refs/cwe")
    def list_cwes() -> Response:
        result = _cache(app).get(lambda: get_service(app).load_cwe_list())
        return jsonify(result)

    @app.get("/api/standards")
    def list_standards() -> Response:
        limit = request.args.get("limit", 500, type=int)
        offset = request.args.get("offset", 0, type=int)
        svc = get_service(app)
        items = [to_camel_dict(s) for s in svc.list_standards()]
        return jsonify(items[offset:offset + limit])

    @app.get("/api/standards/library")
    def list_library() -> Response:
        library = get_library_client(app)
        if library is None:
            return jsonify([])
        try:
            index = library.fetch_index()
        except Exception as exc:
            logger.warning("Failed to fetch library index: %s", exc)
            return error_response("Failed to connect to standards library", 502, "library_error")
        return jsonify(index)

    @app.get("/api/standards/<standard_id>")
    def get_standard(standard_id: str) -> Response:
        svc = get_service(app)
        try:
            detail = svc.get_standard(standard_id)
        except FileNotFoundError:
            return error_response(f"Standard not found: {standard_id}", 404, "not_found")
        return jsonify(to_camel_dict(detail))
