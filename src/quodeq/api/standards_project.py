"""The guard and the two error shapes the per-project standards routes share.

``standards_visibility_routes`` and ``standards_overrides_routes`` both read
and write a file inside the analyzed repository, so both resolve a project id
to its local clone the same way and both refuse a bad body and a rejected
payload the same way. Those three live here rather than once per route
module.
"""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Any

from flask import Response, jsonify

from quodeq.api._assistant_helpers import resolve_repo_root
from quodeq.api._constants import ERROR_CODE_BAD_REQUEST, ERROR_CODE_NOT_FOUND
from quodeq.api.helpers import error_response
from quodeq.shared.validation import validate_path_segment


def project_root_or_error(project_id: str) -> tuple[Path | None, Any]:
    """Validate *project_id* and resolve its local repository root.

    Returns ``(root, None)``, or ``(None, error)`` when the id is malformed
    (400) or the project has no local repository on this machine (404).
    """
    try:
        validate_path_segment(project_id)
    except ValueError:
        return None, error_response("Invalid project id", HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST)
    root = resolve_repo_root(project_id)
    if not root:
        return None, error_response(
            "Project has no local repository", HTTPStatus.NOT_FOUND, ERROR_CODE_NOT_FOUND,
        )
    return Path(root), None


def invalid_body(message: str) -> Any:
    """A 400 naming the body shape the route expects."""
    return error_response(message, HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST)


def invalid_payload(message: str, code: str, errors: list) -> Response:
    """A 400 carrying the per-entry *errors* the validator rejected.

    A jsonified Response rather than an ``error_response`` tuple: these
    routes return the ``details`` list alongside the message.
    """
    resp = jsonify({"error": message, "code": code, "details": errors})
    resp.status_code = HTTPStatus.BAD_REQUEST
    return resp
