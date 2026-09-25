"""Request-body and parameter validation shared by the llm_bridge routes.

Every error these helpers produce is a ready-made ``(response, status)``
pair for the handler to return as-is; None means the input is acceptable.
"""
from __future__ import annotations

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from flask import Response, jsonify, request

from quodeq.api._constants import CODE_INVALID_PARAM, CODE_MISSING_PARAM
from quodeq.api.helpers import json_error
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


def object_body_or_error() -> tuple[dict, None] | tuple[None, tuple[Response, int]]:
    """``(body, None)`` for a JSON object body, else ``(None, 400 response)``."""
    data = json_body()
    if data is None:
        return None, (jsonify(BODY_NOT_OBJECT), HTTPStatus.BAD_REQUEST)
    return data, None


def string_fields_error(data: Mapping[str, Any], names: tuple[str, ...]) -> tuple[Response, int] | None:
    """A 400 for the first of *names* present in *data* with a non-string value.

    An explicit JSON ``null`` is treated as absent, not as a type error,
    matching ``routes_project_create``'s ``x is not None and not isinstance(...)``
    pattern for optional fields.
    """
    for name in names:
        if name in data and data[name] is not None and not isinstance(data[name], str):
            return json_error(f"{name} must be a string", HTTPStatus.BAD_REQUEST, CODE_INVALID_PARAM)
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
        return json_error(err, HTTPStatus.BAD_REQUEST, "INVALID_URL")
    return None


def query_base_url() -> tuple[str | None, tuple[Response, int] | None]:
    """The stripped ``?base_url=`` (None when absent or blank) and its SSRF error, if any."""
    base_url = request.args.get("base_url", "").strip() or None
    err = invalid_base_url(base_url)
    if err is not None:
        return None, err
    return base_url, None


def _invalid_model_name(model: str) -> tuple[Response, int] | None:
    """Return a 400 response when *model* contains invalid characters, else None.

    Prevents path traversal and null-byte injection.
    """
    if "\\" in model or ".." in model or "\0" in model:
        return json_error("Invalid model name", HTTPStatus.BAD_REQUEST, CODE_INVALID_PARAM)
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
            return None, json_error("model is required", HTTPStatus.BAD_REQUEST, CODE_MISSING_PARAM)
    elif not isinstance(model, str):
        return None, json_error("model must be a string", HTTPStatus.BAD_REQUEST, CODE_INVALID_PARAM)
    err = _invalid_model_name(model)
    if err is not None:
        return None, err
    return model, None


def model_request(
    *, require_nonempty: bool,
) -> tuple[dict | None, str | None, tuple[Response, int] | None]:
    """Read a concurrency-test request: ``(body, model, error)``.

    On success *error* is None; otherwise *body* and *model* are None and
    *error* is the 400 for a non-object body or an invalid ``model`` (see
    ``require_model_name`` for *require_nonempty*).
    """
    data, err = object_body_or_error()
    if err is not None:
        return None, None, err
    model, err = require_model_name(data, require_nonempty=require_nonempty)
    if err is not None:
        return None, None, err
    return data, model, None
