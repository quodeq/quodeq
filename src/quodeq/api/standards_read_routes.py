"""GET routes for the Standards Browser & Editor."""
from __future__ import annotations

import logging
import os
import threading
import time as _time

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.core.types import to_camel_dict

logger = logging.getLogger(__name__)

# Module-level mutable cache — reset via reset_cwe_cache() for test isolation.
_cwe_cache: list | None = None
_cwe_cache_time: float = 0.0
_CWE_CACHE_TTL = int(os.environ.get("QUODEQ_CWE_CACHE_TTL", "3600"))  # 1 hour
_cwe_cache_lock = threading.Lock()


def reset_cwe_cache() -> None:
    """Clear the CWE cache. Useful for test isolation."""
    global _cwe_cache, _cwe_cache_time
    _cwe_cache = None
    _cwe_cache_time = 0.0


def _reload_cwe_if_needed(loader) -> list:
    """Return the CWE list, reloading at most once when the cache has expired.

    Uses double-checked locking so the common path (cache is warm) never
    blocks on the lock, and the uncommon path (expired) reloads exactly once
    even when multiple threads race at expiry.
    """
    global _cwe_cache, _cwe_cache_time
    now = _time.monotonic()
    # Fast path: cache is valid — no lock needed.
    if _cwe_cache is not None and (now - _cwe_cache_time) <= _CWE_CACHE_TTL:
        return _cwe_cache
    # Slow path: acquire the lock, then re-check inside it.
    with _cwe_cache_lock:
        now = _time.monotonic()  # re-read after acquiring
        if _cwe_cache is None or (now - _cwe_cache_time) > _CWE_CACHE_TTL:
            _cwe_cache = loader()
            _cwe_cache_time = now
        return _cwe_cache


def register_read_routes(app: Flask, get_service, get_library_client) -> None:
    """Register GET routes for the standards API.

    Args:
        app: The Flask application instance.
        get_service: Factory callable returning the standards service.
        get_library_client: Factory callable returning the library client (or None).
    """

    @app.get("/api/standards/refs/cwe")
    def list_cwes() -> Response:
        result = _reload_cwe_if_needed(lambda: get_service(app).load_cwe_list())
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
