"""POST /api/projects/<project>/refresh: update a project's working copy from its git remote."""
from __future__ import annotations

from http import HTTPStatus

from flask import Response, jsonify

from quodeq.api._constants import CODE_NOT_FOUND
from quodeq.api.helpers import json_error
from quodeq.api.routes_common import reports_dir
from quodeq.core.types.working_copy_refresh import RefreshOutcome
from quodeq.services.base import ActionProvider
from quodeq.services.project_refresh import refresh_project

# Refusals: the HTTP status and the client-safe sentence. The error ``code``
# is the outcome's name, which the UI maps to its own localized text.
_REFUSALS: dict[RefreshOutcome, tuple[HTTPStatus, str]] = {
    RefreshOutcome.NOT_REFRESHABLE: (HTTPStatus.BAD_REQUEST, "This project has no git remote to update from."),
    RefreshOutcome.BUSY: (HTTPStatus.CONFLICT, "This project is being evaluated or updated. Try again when it finishes."),
    RefreshOutcome.DIRTY: (HTTPStatus.CONFLICT, "This folder has uncommitted changes. Update it with git yourself."),
    RefreshOutcome.NO_UPSTREAM: (HTTPStatus.CONFLICT, "The checked-out branch does not track a branch on origin."),
    RefreshOutcome.DIVERGED: (HTTPStatus.CONFLICT, "Local and remote history have diverged. Update it with git yourself."),
    RefreshOutcome.FETCH_FAILED: (HTTPStatus.BAD_GATEWAY, "Could not fetch from the remote."),
}


def handle_refresh_project(provider: ActionProvider, project: str) -> Response | tuple[Response, int]:
    """Refresh *project*'s working copy; see ``services.project_refresh``."""
    result = refresh_project(provider, reports_dir(), project)
    if result is None:
        return json_error("Project not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
    refusal = _REFUSALS.get(result.outcome)
    if refusal is not None:
        status, message = refusal
        body = {"error": message, "code": result.outcome.name, "detail": result.detail}
        return jsonify(body), status
    return jsonify({
        "outcome": result.outcome,
        "newCommits": result.new_commits,
        "lastFetchedAt": result.last_fetched_at,
    })
