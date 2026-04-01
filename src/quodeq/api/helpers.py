"""Shared helpers for action API modules."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, send_from_directory


def error_response(message: str, status: int, code: str) -> tuple[dict[str, Any], int]:
    """Build a standardized error response tuple for Flask endpoints."""
    return {"error": message, "code": code}, status


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

    str_fields = ("discipline", "aiCmd", "aiModel", "subagentModel")
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
            return None
        if resolved.is_file():
            return send_from_directory(str(dist), path)
        if path.startswith('api/'):
            return jsonify({"error": "Not found", "code": "NOT_FOUND"}), HTTPStatus.NOT_FOUND
        return send_from_directory(str(dist), 'index.html')
