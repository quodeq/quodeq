"""GET routes for the Standards Browser & Editor."""
from __future__ import annotations

import http.client
import logging
import threading
import time as _time
from http import HTTPStatus
from typing import Callable

from flask import Flask, Response, jsonify, request

from quodeq.api._constants import ERROR_CODE_BAD_REQUEST, ERROR_CODE_NOT_FOUND
from quodeq.api.helpers import error_response, page_params
from quodeq.shared.env import env_int
from quodeq.shared.serialization import to_camel_dict

logger = logging.getLogger(__name__)

# QUODEQ_CWE_CACHE_TTL: how long (in seconds) the CWE reference list stays
# cached before the next request reloads it. Default 3600 (one hour). Valid
# values are non-negative integers; 0 disables caching (reload every call).
# A non-numeric or negative value is invalid and falls back to the default,
# with a warning logged naming the variable, so a mistyped env value is
# visible instead of silently changing cache behaviour.
_DEFAULT_CWE_CACHE_TTL_S = 3600


def _cache_ttl_from_env(default: int = _DEFAULT_CWE_CACHE_TTL_S) -> int:
    """Read QUODEQ_CWE_CACHE_TTL from the environment; see the module
    comment above for units, default, and valid range.

    ``env_int`` does the parsing, the non-negative check and the warning
    that names the variable, the bad value and the default.
    """
    return env_int("QUODEQ_CWE_CACHE_TTL", default, minimum=0)


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
        self._ttl_s = ttl_s if ttl_s is not None else _cache_ttl_from_env()
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
        """Drop the cached list so the next ``get`` reloads.

        Called after a write that could have changed the CWE data, and by tests
        that would otherwise inherit a warm cache.
        """
        self._cache = None
        self._cache_time = 0.0


def _cache(app: Flask) -> CweCache:
    """The app's CWE cache. ``create_app`` instantiates it; setdefault keeps
    bare test apps (register_read_routes on a plain Flask) working."""
    return app.extensions.setdefault("cwe_cache", CweCache())


_DEFAULT_LIST_LIMIT = 500
_DEFAULT_LIST_OFFSET = 0


def _page_params(args) -> tuple[int, int] | tuple[dict, int]:
    """Parse and validate ``limit``/``offset`` for GET /api/standards.

    Thin wrapper over the shared ``page_params`` so this route keeps its own
    defaults (limit=500, offset=0) and this module's lower-case error code.
    """
    return page_params(
        args,
        default_limit=_DEFAULT_LIST_LIMIT,
        default_offset=_DEFAULT_LIST_OFFSET,
        code=ERROR_CODE_BAD_REQUEST,
    )


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
    def list_standards() -> Response | tuple[dict, int]:
        result = _page_params(request.args)
        if isinstance(result[0], dict):
            return result
        limit, offset = result
        svc = get_service(app)
        page = svc.list_standards()[offset:offset + limit]
        return jsonify([to_camel_dict(s) for s in page])

    @app.get("/api/standards/library")
    def list_library() -> Response:
        library = get_library_client(app)
        if library is None:
            return jsonify([])
        try:
            index = library.fetch_index()
        except (OSError, ValueError, http.client.HTTPException) as exc:
            # OSError covers urllib/ssl transport errors, ValueError covers
            # JSON decode and a non-object body; HTTPException (IncompleteRead,
            # BadStatusLine, ...) is urllib's own family and NOT an OSError.
            logger.warning("Failed to fetch library index: %s", exc)
            return error_response("Failed to connect to standards library", 502, "library_error")
        return jsonify(index)

    @app.get("/api/standards/<standard_id>")
    def get_standard(standard_id: str) -> Response:
        svc = get_service(app)
        try:
            detail = svc.get_standard(standard_id)
        except FileNotFoundError:
            return error_response(f"Standard not found: {standard_id}", HTTPStatus.NOT_FOUND, ERROR_CODE_NOT_FOUND)
        return jsonify(to_camel_dict(detail))
