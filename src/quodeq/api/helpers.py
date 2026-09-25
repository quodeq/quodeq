"""Shared helpers for action API modules."""
from __future__ import annotations

import os
from http import HTTPStatus
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_from_directory

from quodeq.api._constants import CODE_FORBIDDEN, CODE_INVALID_INPUT, CODE_NOT_FOUND, ERROR_CODE_BAD_REQUEST
from quodeq.shared.errors import ClientMessageError  # noqa: F401 -- re-export for api modules


def error_response(message: str, status: int, code: str) -> tuple[dict[str, Any], int]:
    """Build a standardized error response tuple for Flask endpoints."""
    return {"error": message, "code": code}, status


def json_error(message: str, status: int, code: str) -> tuple[Response, int]:
    """``error_response`` already jsonified, as a ``(Response, status)`` tuple.

    For the handlers annotated to return a ``Response``: one call replaces
    the ``body, status = error_response(...)`` plus
    ``return jsonify(body), status`` pair that stood at a hundred-odd sites.
    """
    body, status_code = error_response(message, status, code)
    return jsonify(body), status_code


def json_object_or_error(
    code: str = ERROR_CODE_BAD_REQUEST,
) -> dict[str, Any] | tuple[dict[str, Any], int]:
    """Return the request's JSON object body, or a 400 error tuple.

    A bare ``request.get_json(force=True)`` raises on an unparseable body
    (answering with Werkzeug's default HTML 400 page) and hands back a list
    for ``[]``, whose ``.get`` then raises AttributeError and answers 500.
    The POST handlers share this so a non-JSON and a non-object body both
    come back through their own ``{"error", "code"}`` shape.
    """
    payload = request.get_json(force=True, silent=True)
    if payload is None:
        return error_response("request body must be JSON", HTTPStatus.BAD_REQUEST, code)
    if not isinstance(payload, dict):
        return error_response("Request body must be a JSON object", HTTPStatus.BAD_REQUEST, code)
    return payload


def optional_json_object_or_error(
    code: str = ERROR_CODE_BAD_REQUEST, *, force: bool = False,
) -> dict[str, Any] | tuple[dict[str, Any], int]:
    """Return the JSON object body, ``{}`` when there is none, or a 400 tuple.

    For handlers where every field is optional: no body (or an unparseable
    one) means ``{}``, as the old ``get_json(silent=True) or {}`` did. A body
    that parses to a list or scalar answers a coded 400 instead of reaching
    ``.get`` and answering an HTML 500.

    ``cache=False``: Flask's ``get_json`` caches its parsed result keyed only
    by ``silent``, not by ``force`` -- a bare ``or {}`` call after a
    ``force=True`` one in the same request would otherwise see the earlier
    call's cached body instead of re-checking the content type.
    """
    payload = request.get_json(force=force, silent=True, cache=False)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        return error_response("Request body must be a JSON object", HTTPStatus.BAD_REQUEST, code)
    return payload


def path_from_body(data: dict[str, Any]) -> str | tuple[dict[str, Any], int]:
    """Return the request body's stripped ``path``, or a 400 error tuple.

    Shared by PATCH /api/projects/<project>/path and POST /api/scan so both
    refuse a non-string ``path`` the same way instead of raising
    AttributeError on ``.strip()`` and answering 500. An absent ``path``
    gives ``""``: each route keeps its own required-field message.
    """
    raw = data.get("path", "")
    if not isinstance(raw, str):
        return error_response("path must be a string", HTTPStatus.BAD_REQUEST, CODE_INVALID_INPUT)
    return raw.strip()


_MIN_PAGE_LIMIT = 1
_DEFAULT_PAGE_OFFSET = 0


def _page_int(args, name: str, default: int, minimum: int, kind: str, code: str) -> int | tuple[dict[str, Any], int]:
    """Parse one paging query parameter for :func:`page_params`.

    An absent parameter keeps *default*. A present value that fails
    ``int()``, or is below *minimum*, comes back as a ready
    ``error_response`` result naming the parameter, what was received and
    what is valid.
    """
    raw = args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        # TypeError: request.args only ever holds str, but a direct call
        # with a list or other non-str value must answer the same 400.
        return error_response(f"{name} must be {kind}, got {raw!r}", HTTPStatus.BAD_REQUEST, code)
    if value < minimum:
        return error_response(f"{name} must be {kind}, got {value!r}", HTTPStatus.BAD_REQUEST, code)
    return value


def page_params(
    args,
    *,
    default_limit: int,
    default_offset: int = _DEFAULT_PAGE_OFFSET,
    min_limit: int = _MIN_PAGE_LIMIT,
    code: str = CODE_INVALID_INPUT,
) -> tuple[int, int] | tuple[dict[str, Any], int]:
    """Parse and validate ``limit``/``offset`` for a paginated route.

    Returns ``(limit, offset)``, or an ``error_response`` result whose first
    element is a dict, which is how callers tell the two apart. Every
    paginated route shares one rule: an absent parameter keeps the route's
    default, and a parameter that IS present but is not an integer or is
    below its minimum answers 400 naming the parameter, instead of silently
    substituting the default the way ``request.args.get(..., type=int)``
    did.

    *min_limit* is 0 for the routes where ``limit=0`` is the "no limit"
    sentinel, and *code* covers the modules whose error codes are
    lower-case. A route's own upper cap stays a clamp in the route: asking
    for more than it serves is not an error.
    """
    limit_kind = "a positive integer" if min_limit > 0 else "a non-negative integer"
    limit = _page_int(args, "limit", default_limit, min_limit, limit_kind, code)
    if isinstance(limit, tuple):
        return limit
    offset = _page_int(args, "offset", default_offset, 0, "a non-negative integer", code)
    if isinstance(offset, tuple):
        return offset
    return limit, offset


def sanitize_for_log(value: str) -> str:
    """Remove CR/LF from a value before including it in a log message.

    Prevents log forging when client-supplied values contain embedded
    newlines that would create fake log entries.
    """
    return value.replace("\r", "").replace("\n", "")


_BLOCKED_SCAN_PATHS = ("/proc", "/sys", "/dev", "/etc", "/var/run", "/private/etc", "/private/var/run")


def scan_target_error(target_path: Path | str, reports_root: str) -> tuple[dict[str, Any], int] | None:
    """Validate a directory path against the scan allowlist.

    Shared by /api/scan, create_project's local-repo branch, and
    start_evaluation so all enforce the same rules: the path must live under
    the user's home or the evaluations directory, and must not be a blocked
    system path. Returns an ``error_response`` tuple on rejection, or None
    when the path is allowed.

    Uses the realpath + startswith form (not pathlib is_relative_to) — it is
    the containment shape CodeQL/Snyk recognize as a barrier.
    """
    candidate = os.path.realpath(str(target_path))
    _allowed_roots = (os.path.realpath(str(Path.home())), os.path.realpath(reports_root))
    if not any(candidate == root or candidate.startswith(root + os.sep) for root in _allowed_roots):
        return error_response(
            "Scan path must be under home directory", HTTPStatus.FORBIDDEN, CODE_FORBIDDEN,
        )
    # Block scanning system directories to prevent information disclosure
    if any(candidate.startswith(b) for b in _BLOCKED_SCAN_PATHS):
        return error_response("Cannot scan system directories", HTTPStatus.FORBIDDEN, CODE_FORBIDDEN)
    return None


def validate_evaluation_payload(payload: dict[str, Any]) -> str | None:
    """Validate the evaluate request payload.

    Returns an error message string if validation fails, or ``None`` if valid.
    Required fields: ``repo`` (non-empty string).
    Optional typed fields: ``discipline`` (str), ``dimensions`` (str),
    ``numerical`` (bool), ``aiCmd`` (str), ``aiModel`` (str),
    ``subagentModel`` (str).
    """
    missing: list[str] = []
    invalid: list[str] = []

    repo = payload.get("repo")
    if not repo:
        missing.append("repo")
    elif not isinstance(repo, str):
        invalid.append("repo (must be a string)")

    # dimensions accepts both string ("a,b") and array (["a","b"]) from frontend
    dims = payload.get("dimensions")
    if dims is not None:
        if isinstance(dims, list):
            payload["dimensions"] = ",".join(str(d) for d in dims)
        elif not isinstance(dims, str):
            invalid.append("dimensions (must be a string or array of strings)")

    str_fields = ("discipline", "aiCmd", "aiCmdPath", "aiModel", "subagentModel")
    for field in str_fields:
        value = payload.get(field)
        if value is not None and not isinstance(value, str):
            invalid.append(f"{field} (must be a string)")

    numerical = payload.get("numerical")
    if numerical is not None and not isinstance(numerical, bool):
        invalid.append("numerical (must be a boolean)")

    parts: list[str] = []
    if missing:
        parts.append(f"missing required fields: {', '.join(missing)}")
    if invalid:
        parts.append(f"invalid fields: {', '.join(invalid)}")
    return "; ".join(parts) if parts else None


def register_static_routes(app: Flask, static_dist: str | None) -> None:
    """Register static file serving routes."""
    if not static_dist:
        return
    dist = Path(static_dist).resolve()
    if not dist.is_dir():
        return

    @app.route('/')
    def serve_root() -> Response:
        """Serve the SPA index page."""
        return send_from_directory(str(dist), 'index.html')

    @app.route('/<path:path>')
    def serve_static_or_spa(path: str) -> Response | tuple[Response, int]:
        """Serve a static file or fall back to the SPA index."""
        resolved = (dist / path).resolve()
        if not resolved.is_relative_to(dist):
            return jsonify({"error": "Forbidden", "code": CODE_FORBIDDEN}), HTTPStatus.FORBIDDEN
        if resolved.is_file():
            return send_from_directory(str(dist), path)
        if path.startswith('api/'):
            return jsonify({"error": "Not found", "code": CODE_NOT_FOUND}), HTTPStatus.NOT_FOUND
        return send_from_directory(str(dist), 'index.html')
