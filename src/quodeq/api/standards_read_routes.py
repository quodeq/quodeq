"""GET routes for the Standards Browser & Editor."""
from __future__ import annotations

import logging
import time as _time

from flask import Flask, Response, jsonify

from quodeq.api.helpers import error_response
from quodeq.core.types import to_camel_dict

logger = logging.getLogger(__name__)

_cwe_cache: list | None = None
_cwe_cache_time: float = 0.0
_CWE_CACHE_TTL = 3600  # 1 hour


def reset_cwe_cache() -> None:
    """Clear the CWE cache. Useful for test isolation."""
    global _cwe_cache, _cwe_cache_time
    _cwe_cache = None
    _cwe_cache_time = 0.0


def register_read_routes(app: Flask, get_service, get_library_client) -> None:
    """Register GET routes for the standards API.

    Args:
        app: The Flask application instance.
        get_service: Factory callable returning the standards service.
        get_library_client: Factory callable returning the library client (or None).
    """

    @app.get("/api/standards/refs/cwe")
    def list_cwes() -> Response:
        global _cwe_cache, _cwe_cache_time
        now = _time.monotonic()
        if _cwe_cache is None or (now - _cwe_cache_time) > _CWE_CACHE_TTL:
            _cwe_cache = get_service(app).load_cwe_list()
            _cwe_cache_time = now
        return jsonify(_cwe_cache)

    @app.get("/api/standards")
    def list_standards() -> Response:
        svc = get_service(app)
        return jsonify([to_camel_dict(s) for s in svc.list_standards()])

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
