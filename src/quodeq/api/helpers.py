"""Shared helpers for action API modules."""
from __future__ import annotations

import os
from http import HTTPStatus
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, send_from_directory


def error_response(message: str, status: int, code: str) -> tuple[dict[str, Any], int]:
    """Build a standardized error response tuple for Flask endpoints."""
    return {"error": message, "code": code}, status


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
            "Scan path must be under home directory", HTTPStatus.FORBIDDEN, "FORBIDDEN",
        )
    # Block scanning system directories to prevent information disclosure
    if any(candidate.startswith(b) for b in _BLOCKED_SCAN_PATHS):
        return error_response("Cannot scan system directories", HTTPStatus.FORBIDDEN, "FORBIDDEN")
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
            return jsonify({"error": "Forbidden", "code": "FORBIDDEN"}), HTTPStatus.FORBIDDEN
        if resolved.is_file():
            return send_from_directory(str(dist), path)
        if path.startswith('api/'):
            return jsonify({"error": "Not found", "code": "NOT_FOUND"}), HTTPStatus.NOT_FOUND
        return send_from_directory(str(dist), 'index.html')
