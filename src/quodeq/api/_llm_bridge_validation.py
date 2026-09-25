"""Request-body and parameter validation shared by the llm_bridge routes.

Split out of ``llm_bridge_routes.py`` to keep that module under the size
limit. Every helper returns a ready-made ``(response, status)`` pair for the
handler to return as-is, or None when the input is acceptable.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flask import Response, jsonify, request

from quodeq.api._constants import CODE_INVALID_PARAM
from quodeq.shared.url_validation import url_safety_error

BODY_NOT_OBJECT = {"error": "request body must be a JSON object", "code": CODE_INVALID_PARAM}


def json_body() -> dict | None:
    """Return the request's JSON body when it is an object, else None.

    A body like ``[1]`` or ``"x"`` parses as valid JSON but crashes the
    ``data.get(...)`` calls in the handlers with an AttributeError (a 500);
    callers turn None into a 400 instead.
    """
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def string_fields_error(data: Mapping[str, Any], names: tuple[str, ...]) -> tuple[Response, int] | None:
    """A 400 for the first of *names* present in *data* with a non-string value.

    An explicit JSON ``null`` is treated as absent, not as a type error,
    matching ``routes_project_create``'s ``x is not None and not isinstance(...)``
    pattern for optional fields.
    """
    for name in names:
        if name in data and data[name] is not None and not isinstance(data[name], str):
            return jsonify({"error": f"{name} must be a string", "code": "INVALID_PARAM"}), 400
    return None


def invalid_base_url(base_url: str | None) -> tuple[Response, int] | None:
    """Return a 400 response when *base_url* fails SSRF validation, else None.

    Same policy as /api/provider/test: http(s) scheme only, private/LAN
    addresses allowed (self-hosted omlx servers are the normal case).
    """
    if base_url is None:
        return None
    err = url_safety_error(base_url, allow_private=True)
    if err is not None:
        return jsonify({"error": err, "code": "INVALID_URL"}), 400
    return None


def _invalid_model_name(model: str) -> tuple[Response, int] | None:
    """Return a 400 response when *model* contains invalid characters, else None.

    Prevents path traversal and null-byte injection.
    """
    if "\\" in model or ".." in model or "\0" in model:
        return jsonify({"error": "Invalid model name", "code": CODE_INVALID_PARAM}), 400
    return None


def require_model_name(
    data: dict, *, require_nonempty: bool,
) -> tuple[str | None, tuple[Response, int] | None]:
    """Validate the ``model`` field shared by the concurrency-test routes.

    ollama requires a non-empty string (``require_nonempty=True``, rejects
    ``""`` with MISSING_PARAM); llamacpp and omlx accept an empty string and
    only reject non-strings (``require_nonempty=False``, INVALID_PARAM).
    """
    model = data.get("model", "")
    if require_nonempty:
        if not model or not isinstance(model, str):
            return None, (jsonify({"error": "model is required", "code": "MISSING_PARAM"}), 400)
    elif not isinstance(model, str):
        return None, (jsonify({"error": "model must be a string", "code": CODE_INVALID_PARAM}), 400)
    err = _invalid_model_name(model)
    if err is not None:
        return None, err
    return model, None
