"""Discovery routes: AI clients, plugins, and filesystem browsing."""
from __future__ import annotations

from http import HTTPStatus

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.core.types import to_camel_dict
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
        body, status = error_response(safe_msg, http_status, code)
        return jsonify(body), status
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
    """
    data = request.get_json(silent=True) or {}
    parent = data.get("path", "").strip()
    name = data.get("name", "").strip()
    payload = provider.browse_mkdir(parent, name)
    if "error" in payload:
        http_status, code = _MKDIR_ERROR_MAP.get(
            payload.get("error_code"),
            (HTTPStatus.INTERNAL_SERVER_ERROR, "SERVER_ERROR"),
        )
        body, status = error_response(payload["error"], http_status, code)
        return jsonify(body), status
    return jsonify(payload)


def register_discovery_routes(app: Flask, provider: ActionProvider) -> None:
    """Register /api/ai-clients/*, /api/plugins, /api/browse routes."""

    @app.get("/api/ai-clients")
    def ai_clients() -> Response:
        return jsonify(provider.get_ai_clients())

    @app.get("/api/ai-clients/<client_id>/models")
    def client_models(client_id: str) -> Response:
        return jsonify(provider.get_client_models(client_id))

    @app.get("/api/plugins")
    def plugins() -> Response:
        return jsonify([to_camel_dict(p) for p in discover_plugins()])

    @app.get("/api/browse")
    def browse() -> Response | tuple[Response, int]:
        return _handle_browse(provider)

    @app.post("/api/browse/mkdir")
    def browse_mkdir() -> Response | tuple[Response, int]:
        return _handle_browse_mkdir(provider)
