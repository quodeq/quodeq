"""Discovery routes: AI clients, plugins, and filesystem browsing."""
from __future__ import annotations

from http import HTTPStatus

from flask import Flask, Response, jsonify, request

from quodeq.api._evaluation_helpers import ai_cmd_path_error
from quodeq.api.helpers import json_error, optional_json_object_or_error
from quodeq.shared.serialization import to_camel_dict
from quodeq.services.base import ActionProvider
from quodeq.services.plugin_discovery import discover_plugins

# Provider browse error codes -> (HTTP status, API error code, safe message).
# Keyed by error_code (not message substring) so the frozen response bodies
# stay exact regardless of the provider's internal wording. .get() defaults
# to the same 404 triple browse_repo returns for an unrecognized code.
_BROWSE_ERROR_MAP = {
    "PATH_OUTSIDE_BOUNDARY": (HTTPStatus.FORBIDDEN, "FORBIDDEN", "Path must be within the user's home directory"),
    "PATH_NOT_DIRECTORY": (HTTPStatus.BAD_REQUEST, "INVALID_INPUT", "Path is not a directory"),
    "PATH_NOT_FOUND": (HTTPStatus.NOT_FOUND, "INVALID_INPUT", "Path not found or not accessible"),
}
_BROWSE_ERROR_DEFAULT = (HTTPStatus.NOT_FOUND, "INVALID_INPUT", "Path not found or not accessible")


def _handle_browse(provider: ActionProvider) -> Response | tuple[Response, int]:
    """Handle GET /api/browse."""
    path = request.args.get("path")
    include_files = request.args.get("files", "").lower() in ("1", "true")
    payload = provider.browse_repo(path, include_files=include_files)
    if "error" in payload:
        http_status, code, safe_msg = _BROWSE_ERROR_MAP.get(
            payload.get("error_code"), _BROWSE_ERROR_DEFAULT,
        )
        return json_error(safe_msg, http_status, code)
    return jsonify(payload)


# Provider mkdir error codes -> (HTTP status, API error code). The messages
# come through verbatim from the provider so the responses stay identical to
# when this handler did the filesystem work itself.
_MKDIR_ERROR_MAP = {
    "MISSING_FIELDS": (HTTPStatus.BAD_REQUEST, "INVALID_INPUT"),
    "INVALID_NAME": (HTTPStatus.BAD_REQUEST, "INVALID_INPUT"),
    "PATH_OUTSIDE_BOUNDARY": (HTTPStatus.FORBIDDEN, "FORBIDDEN"),
    "PARENT_NOT_FOUND": (HTTPStatus.NOT_FOUND, "NOT_FOUND"),
    "ALREADY_EXISTS": (HTTPStatus.CONFLICT, "CONFLICT"),
    "MKDIR_FAILED": (HTTPStatus.INTERNAL_SERVER_ERROR, "SERVER_ERROR"),
}


def _handle_browse_mkdir(provider: ActionProvider) -> Response | tuple[Response, int]:
    """Handle POST /api/browse/mkdir — create a new subdirectory.

    Validation and the mkdir itself live in the provider (mirroring
    ``_handle_browse``); this handler only shapes the HTTP response.
    Body fields are type-checked before ``.strip()`` so a null or
    non-string value is treated as missing rather than raising an
    unhandled 500; a non-object body answers a coded 400.
    """
    data = optional_json_object_or_error("INVALID_INPUT")
    if not isinstance(data, dict):
        return jsonify(data[0]), data[1]
    parent = data.get("path")
    parent = parent.strip() if isinstance(parent, str) else ""
    name = data.get("name")
    name = name.strip() if isinstance(name, str) else ""
    payload = provider.browse_mkdir(parent, name)
    if "error" in payload:
        http_status, code = _MKDIR_ERROR_MAP.get(
            payload.get("error_code"),
            (HTTPStatus.INTERNAL_SERVER_ERROR, "SERVER_ERROR"),
        )
        return json_error(payload["error"], http_status, code)
    return jsonify(payload)


def register_discovery_routes(app: Flask, provider: ActionProvider) -> None:
    """Register /api/ai-clients/*, /api/plugins, /api/browse routes."""

    @app.get("/api/ai-clients")
    def ai_clients() -> Response:
        return jsonify(provider.get_ai_clients())

    @app.get("/api/ai-clients/<client_id>/models")
    def client_models(client_id: str) -> Response | tuple[Response, int]:
        payload = provider.get_client_models(client_id)
        if "error" in payload:
            return json_error(payload["error"], HTTPStatus.SERVICE_UNAVAILABLE, payload["error_code"])
        return jsonify(payload)

    @app.get("/api/ai-clients/<client_id>/cmd-path-check")
    def client_cmd_path_check(client_id: str) -> Response:
        """Eager check for the Settings command override field.

        Same rules as the aiCmdPath validation on POST /api/evaluations,
        returned as data so the UI can flag a bad value when it is typed
        instead of when a start fails.
        """
        reason = ai_cmd_path_error(client_id, request.args.get("path"))
        return jsonify({
            "ok": reason is None,
            "error": reason,
            "code": None if reason is None else "INVALID_INPUT",
        })

    @app.get("/api/plugins")
    def plugins() -> Response:
        return jsonify([to_camel_dict(p) for p in discover_plugins()])

    @app.get("/api/browse")
    def browse() -> Response | tuple[Response, int]:
        return _handle_browse(provider)

    @app.post("/api/browse/mkdir")
    def browse_mkdir() -> Response | tuple[Response, int]:
        return _handle_browse_mkdir(provider)
