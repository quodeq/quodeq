"""The ``url`` field of a JSON request body, required and stripped."""
from __future__ import annotations

from http import HTTPStatus

from flask import Response

from quodeq.api._constants import CODE_INVALID_INPUT, CODE_URL_REQUIRED
from quodeq.api.helpers import json_error, optional_json_object_or_response


def required_url_or_error() -> str | tuple[Response, int]:
    """The stripped ``url`` of the JSON body, or the 400 a handler returns as-is."""
    body = optional_json_object_or_response(CODE_INVALID_INPUT)
    if not isinstance(body, dict):
        return body
    url = str(body.get("url") or "").strip()
    if not url:
        return json_error("url is required", HTTPStatus.BAD_REQUEST, CODE_URL_REQUIRED)
    return url
