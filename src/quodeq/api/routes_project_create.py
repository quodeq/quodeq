"""POST /api/projects — register a new project (clone + scan).

Split from ``routes_project_list.py`` to keep that file under the size
ratchet's 300-line cap. ``reports_dir`` is looked up dynamically through the
routes_project_list facade (rather than imported directly) so that
``patch("quodeq.api.routes_project_list.reports_dir", ...)`` in existing
tests still takes effect, since ``_create_project`` is invoked from a
closure registered by ``register_project_list_routes``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path

from flask import Response, jsonify, request

from quodeq.api.helpers import error_response, scan_target_error as _scan_target_error
from quodeq.services.base import ActionProvider, NewProjectSpec
from quodeq.shared.validation import contained_path, validate_relative_scope


def _reports_dir() -> str:
    from quodeq.api import routes_project_list as _facade
    return _facade.reports_dir()


@dataclass
class _CreateProjectRequest:
    repo: str
    discipline: str | None
    scope_path: str | None
    clone_dest: str | None
    ephemeral: bool
    reports_root: str
    is_url: bool


def _parse_create_project_request(
    data: dict,
) -> tuple[_CreateProjectRequest | None, tuple[Response, int] | None]:
    """Parse and validate the create_project request body. Returns
    (parsed, error): parsed is None on failure, error is None on success."""
    repo = (data.get("repo") or "").strip()
    if not repo:
        body, status = error_response("repo is required", HTTPStatus.BAD_REQUEST, "MISSING_REPO")
        return None, (jsonify(body), status)

    scope_path = data.get("scopePath") or None
    if scope_path is not None:
        try:
            validate_relative_scope(str(scope_path))
        except ValueError as exc:
            body, status = error_response(str(exc), HTTPStatus.BAD_REQUEST, "INVALID_SCOPE")
            return None, (jsonify(body), status)
    discipline = data.get("discipline") or None
    clone_dest = data.get("cloneDest") or None
    ephemeral = bool(data.get("ephemeral", False))
    reports_root = _reports_dir()

    from quodeq.shared.utils import is_repo_url
    try:
        is_url = is_repo_url(repo)
    except ValueError:
        body, status = error_response("Invalid repo URL", HTTPStatus.BAD_REQUEST, "INVALID_REPO_URL")
        return None, (jsonify(body), status)

    return _CreateProjectRequest(
        repo=repo, discipline=discipline, scope_path=scope_path,
        clone_dest=clone_dest, ephemeral=ephemeral,
        reports_root=reports_root, is_url=is_url,
    ), None


def _resolve_create_project_clone_dest(
    ephemeral: bool, clone_dest: str | None,
) -> tuple[str | None, tuple[Response, int] | None]:
    """For a URL repo, resolve/validate cloneDest. Returns (resolved_clone_dest, error)."""
    if not ephemeral and not clone_dest:
        body, status = error_response(
            "cloneDest is required for URL repos when ephemeral is false",
            HTTPStatus.BAD_REQUEST,
            "MISSING_CLONE_DEST",
        )
        return None, (jsonify(body), status)
    if not ephemeral and clone_dest:
        try:
            # Containment and the directory check both live in the try
            # so every rejection exits here. Falling through past a
            # failed containment check on a sentinel would leave the
            # unguarded value live on one path.
            dest = contained_path(clone_dest, Path.home())
            if not os.path.isdir(dest):
                raise ValueError("cloneDest is not an existing directory")
        except OSError:
            body, status = error_response(
                "Invalid cloneDest path",
                HTTPStatus.BAD_REQUEST,
                "INVALID_CLONE_DEST",
            )
            return None, (jsonify(body), status)
        except ValueError:
            body, status = error_response(
                "cloneDest must be an existing directory under your home folder",
                HTTPStatus.BAD_REQUEST,
                "INVALID_CLONE_DEST",
            )
            return None, (jsonify(body), status)
        # Hand the *contained* path to the cloner. The previous code
        # resolved into a local and then passed the raw request string
        # on, so the check guarded a value nothing downstream used.
        return dest, None
    return clone_dest, None


def _validate_local_create_project_repo(repo: str, reports_root: str) -> tuple[Response, int] | None:
    # For local repos, fail fast if the path doesn't exist — registering
    # a project for a missing directory would leave an orphan UUID dir
    # behind that the caller has no way to recover from.
    local_candidate = Path(repo)
    if not local_candidate.exists() or not local_candidate.is_dir():
        # Say WHICH mistake it was: a path at a file is a different
        # user error from a missing path (a real registration once
        # slipped through as .../lib/player.js).
        detail = (
            "points at a file, not a directory"
            if local_candidate.exists()
            else "does not exist"
        )
        body, status = error_response(
            f"Local repo path {detail}",
            HTTPStatus.BAD_REQUEST,
            "INVALID_REPO",
        )
        return jsonify(body), status
    # Same allowlist as /api/scan: registering a project scans it and
    # persists the file tree, so an unvalidated path here would leak
    # arbitrary readable directories through project endpoints.
    err = _scan_target_error(local_candidate.resolve(), reports_root)
    if err is not None:
        body, status = err
        return jsonify(body), status
    return None


def _create_project_error_response(result) -> tuple[Response, int] | None:
    """Map a non-success ActionProvider.create_project result to an error
    response. Returns None for a successful result (caller handles that)."""
    if result.status == "duplicate":
        return (
            jsonify({"error": "Project already exists", "existingProjectId": result.existing_project_id}),
            HTTPStatus.CONFLICT,
        )
    if result.status == "invalid_repo":
        body, status = error_response(result.message, HTTPStatus.BAD_REQUEST, "INVALID_REPO")
        return jsonify(body), status
    if result.status == "clone_failed":
        code_map = {
            "auth": ("AUTH_REQUIRED", HTTPStatus.BAD_REQUEST),
            "network": ("NETWORK_ERROR", HTTPStatus.BAD_GATEWAY),
            "repo_not_found": ("REPO_NOT_FOUND", HTTPStatus.NOT_FOUND),
            "dest_exists": ("DEST_EXISTS", HTTPStatus.CONFLICT),
            "disk": ("DISK_ERROR", HTTPStatus.INSUFFICIENT_STORAGE),
            "unknown": ("CLONE_FAILED", HTTPStatus.BAD_GATEWAY),
        }
        code, status = code_map.get(result.clone_error_kind, ("CLONE_FAILED", HTTPStatus.BAD_GATEWAY))
        body, _ = error_response(result.message, status, code)
        return jsonify(body), status
    if result.status == "internal_error":
        # Return a generic message; the exception detail (which can carry
        # filesystem paths or backend internals) is already logged by the
        # provider, not sent to the remote caller.
        body, status = error_response(
            "Registration failed due to an internal error.",
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "REGISTRATION_FAILED",
        )
        return jsonify(body), status
    return None


def _create_project(provider: ActionProvider) -> Response | tuple[Response, int]:
    """Register a new project (clone + scan) without starting an evaluation.

    Body: ``{ repo, cloneDest?, ephemeral?, branch?, scopePath?, discipline? }``

    For URL repos: requires either ``cloneDest`` (existing dir under home)
    or ``ephemeral: true``. For local-path repos: ``cloneDest`` and
    ``ephemeral`` are ignored.
    """
    data = request.get_json(silent=True) or {}
    parsed, error = _parse_create_project_request(data)
    if error is not None:
        return error

    clone_dest = parsed.clone_dest
    if parsed.is_url:
        clone_dest, clone_err = _resolve_create_project_clone_dest(parsed.ephemeral, clone_dest)
        if clone_err is not None:
            return clone_err
    else:
        local_err = _validate_local_create_project_repo(parsed.repo, parsed.reports_root)
        if local_err is not None:
            return local_err

    spec = NewProjectSpec(
        repo=parsed.repo, discipline=parsed.discipline, scope_path=parsed.scope_path,
        clone_dest=clone_dest, ephemeral=parsed.ephemeral,
    )
    result = provider.create_project(parsed.reports_root, spec)

    error = _create_project_error_response(result)
    if error is not None:
        return error

    # The 5s ProjectsCache would otherwise hide the new project from an
    # immediately-following GET /api/projects (the wizard refetches the
    # list as soon as it closes).
    provider.invalidate_projects_cache()
    return jsonify({"projectId": result.project_id, "scanData": result.scan_data})
