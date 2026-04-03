"""Discovery routes: AI clients, plugins, and filesystem browsing."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.core.types import to_camel_dict
from quodeq.services.base import ActionProvider

# Error keyword returned by browse_repo when the path exists but is not a directory.
_BROWSE_NOT_A_DIR_KEYWORD = "not a directory"


def _handle_browse(provider: ActionProvider) -> Response | tuple[Response, int]:
    """Handle GET /api/browse."""
    path = request.args.get("path")
    if path:
        resolved = Path(path).resolve()
        home = Path.home().resolve()
        if not resolved.is_relative_to(home):
            body, status = error_response(
                "Path must be within the user's home directory",
                HTTPStatus.FORBIDDEN,
                "FORBIDDEN",
            )
            return jsonify(body), status
    payload = provider.browse_repo(path)
    if "error" in payload:
        raw_error = payload["error"]
        is_not_dir = _BROWSE_NOT_A_DIR_KEYWORD in raw_error.lower()
        browse_status = HTTPStatus.BAD_REQUEST if is_not_dir else HTTPStatus.NOT_FOUND
        safe_msg = "Path is not a directory" if is_not_dir else "Path not found or not accessible"
        body, status = error_response(safe_msg, browse_status, "INVALID_INPUT")
        return jsonify(body), status
    return jsonify(payload)


def _handle_browse_mkdir() -> Response | tuple[Response, int]:
    """Handle POST /api/browse/mkdir — create a new subdirectory."""
    data = request.get_json(silent=True) or {}
    parent = data.get("path", "").strip()
    name = data.get("name", "").strip()
    if not parent or not name:
        body, status = error_response("path and name are required", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
        return jsonify(body), status
    if "/" in name or "\\" in name or name in (".", ".."):
        body, status = error_response("Invalid folder name", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
        return jsonify(body), status
    resolved = Path(parent).resolve()
    home = Path.home().resolve()
    if not resolved.is_relative_to(home):
        body, status = error_response(
            "Path must be within the user's home directory",
            HTTPStatus.FORBIDDEN,
            "FORBIDDEN",
        )
        return jsonify(body), status
    if not resolved.is_dir():
        body, status = error_response("Parent path not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        return jsonify(body), status
    target = resolved / name
    try:
        target.mkdir(parents=False, exist_ok=False)
    except FileExistsError:
        body, status = error_response("Folder already exists", HTTPStatus.CONFLICT, "CONFLICT")
        return jsonify(body), status
    except OSError as exc:
        body, status = error_response(f"Could not create folder: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR, "SERVER_ERROR")
        return jsonify(body), status
    return jsonify({"created": True, "path": str(target)})


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
        from quodeq.services.plugin_discovery import discover_plugins  # deferred: avoid circular import at module level
        return jsonify([to_camel_dict(p) for p in discover_plugins()])

    @app.get("/api/browse")
    def browse() -> Response | tuple[Response, int]:
        return _handle_browse(provider)

    @app.post("/api/browse/mkdir")
    def browse_mkdir() -> Response | tuple[Response, int]:
        return _handle_browse_mkdir()
