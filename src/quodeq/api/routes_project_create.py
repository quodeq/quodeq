"""POST /api/projects — register a new project (clone + scan).

``reports_dir`` is looked up dynamically through its
real owner, ``routes_common`` (rather than through the ``routes_project_list``
facade that just re-exports it), so this module never imports back a sibling
that imports it. Tests patch "quodeq.api.routes_common.reports_dir".
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path

from flask import Response, jsonify

from quodeq.api._constants import (
    CODE_INVALID_CLONE_DEST, CODE_INVALID_DISCIPLINE, CODE_INVALID_INPUT, CODE_INVALID_REPO,
    CODE_PROJECT_EXISTS)
from quodeq.api._llm_bridge_validation import bool_fields_error
from quodeq.api.helpers import (
    json_error,
    jsonify_error,
    optional_json_object_or_response,
    scan_target_error as _scan_target_error,
)
from quodeq.api.routes_github_access import access_failure_response
from quodeq.api.routes_project_clone import start_clone_job
from quodeq.config.clone_env import default_clone_root
from quodeq.services.base import ActionProvider, CreateProjectStatus, NewProjectSpec
from quodeq.services.clone_codes import clone_code_for
from quodeq.services.github_access import forget_url, resolve_access
from quodeq.shared.git_errors import output_tail
from quodeq.shared.paths import not_a_directory_reason
from quodeq.shared.utils import is_repo_url
from quodeq.shared.validation import contained_path, relative_scope_error


def _reports_dir() -> str:
    from quodeq.api.routes_common import reports_dir as _owner_reports_dir
    return _owner_reports_dir()


@dataclass
class CreateProjectRequest:
    """A validated POST /api/projects body, parsed once at the request boundary."""

    repo: str
    discipline: str | None
    scope_path: str | None
    clone_dest: str | None
    ephemeral: bool
    reports_root: str
    is_url: bool


def _parse_create_project_request(
    data: dict,
) -> tuple[CreateProjectRequest | None, tuple[Response, int] | None]:
    """Parse and validate the create_project request body. Returns
    (parsed, error): parsed is None on failure, error is None on success."""
    raw_repo = data.get("repo")
    if raw_repo is not None and not isinstance(raw_repo, str):
        return None, json_error("repo must be a string", HTTPStatus.BAD_REQUEST, CODE_INVALID_REPO)
    repo = (raw_repo or "").strip()
    if not repo:
        return None, json_error("repo is required", HTTPStatus.BAD_REQUEST, "MISSING_REPO")

    scope_path = data.get("scopePath") or None
    if scope_path is not None:
        err = relative_scope_error(str(scope_path))
        if err is not None:
            return None, json_error(err, HTTPStatus.BAD_REQUEST, "INVALID_SCOPE")
    discipline = data.get("discipline")
    if discipline is not None and not isinstance(discipline, str):
        return None, json_error("discipline must be a string", HTTPStatus.BAD_REQUEST, CODE_INVALID_DISCIPLINE)
    discipline = discipline or None
    clone_dest = data.get("cloneDest")
    if clone_dest is not None and not isinstance(clone_dest, str):
        return None, json_error("cloneDest must be a string", HTTPStatus.BAD_REQUEST, CODE_INVALID_CLONE_DEST)
    clone_dest = clone_dest or None
    bool_error = bool_fields_error(data, ("ephemeral",))
    if bool_error is not None:
        return None, bool_error
    ephemeral = bool(data.get("ephemeral", False))
    reports_root = _reports_dir()

    try:
        is_url = is_repo_url(repo)
    except ValueError:
        return None, json_error("Invalid repo URL", HTTPStatus.BAD_REQUEST, "INVALID_REPO_URL")

    return CreateProjectRequest(
        repo=repo, discipline=discipline, scope_path=scope_path,
        clone_dest=clone_dest, ephemeral=ephemeral,
        reports_root=reports_root, is_url=is_url,
    ), None


def _expand_home(clone_dest: str) -> str:
    """``~`` and ``~/...`` mean the user's home folder, the same ``Path.home()``
    the containment check uses (not ``$HOME`` via expanduser, which can differ)."""
    if clone_dest == "~":
        return str(Path.home())
    if clone_dest.startswith("~/"):
        return str(Path.home() / clone_dest[2:])
    return clone_dest


def _ensure_default_clone_root() -> tuple[str | None, tuple[Response, int] | None]:
    """No cloneDest sent: the configured root (QUODEQ_REPOS_DIR may sit
    outside home) is the operator's choice, so it is trusted and created on
    demand. A failure names the default folder, not a cloneDest nobody sent."""
    dest = str(default_clone_root())
    try:
        os.makedirs(dest, exist_ok=True)
        created = os.path.isdir(dest)
    except OSError:
        created = False
    if created:
        return dest, None
    return None, json_error(
        "The default working-copy folder could not be created",
        HTTPStatus.BAD_REQUEST,
        CODE_INVALID_CLONE_DEST,
    )


def _resolve_create_project_clone_dest(
    ephemeral: bool, clone_dest: str | None,
) -> tuple[str | None, tuple[Response, int] | None]:
    """For a URL repo, resolve/validate cloneDest. Returns (resolved_clone_dest, error).

    An absent cloneDest means the default working-copy root, created on demand.
    """
    if ephemeral:
        return clone_dest, None
    if not clone_dest:
        return _ensure_default_clone_root()
    try:
        # Containment and the directory check both live in the try
        # so every rejection exits here. Falling through past a
        # failed containment check on a sentinel would leave the
        # unguarded value live on one path. A leading "~" is the old
        # wizard default and means the home folder; a missing folder
        # under home is created, the way the default root is.
        dest = contained_path(_expand_home(clone_dest), Path.home())
        if os.path.exists(dest) and not os.path.isdir(dest):
            raise ValueError("cloneDest is not a directory")
        os.makedirs(dest, exist_ok=True)
        if not os.path.isdir(dest):
            raise ValueError("cloneDest is not an existing directory")
    except OSError:
        return None, json_error(
            "Invalid cloneDest path",
            HTTPStatus.BAD_REQUEST,
            CODE_INVALID_CLONE_DEST,
        )
    except ValueError:
        return None, json_error(
            "cloneDest must be an existing directory under your home folder",
            HTTPStatus.BAD_REQUEST,
            CODE_INVALID_CLONE_DEST,
        )
    # Hand the *contained* path to the cloner, not the raw request string,
    # so the check guards the value everything downstream uses.
    return dest, None


def _validate_local_create_project_repo(repo: str, reports_root: str) -> tuple[Response, int] | None:
    # For local repos, fail fast if the path doesn't exist — registering
    # a project for a missing directory would leave an orphan UUID dir
    # behind that the caller has no way to recover from.
    local_candidate = Path(repo)
    if not local_candidate.is_dir():
        return json_error(
            f"Local repo path {not_a_directory_reason(local_candidate)}",
            HTTPStatus.BAD_REQUEST,
            CODE_INVALID_REPO,
        )
    # Same allowlist as /api/scan: registering a project scans it and
    # persists the file tree, so an unvalidated path here would leak
    # arbitrary readable directories through project endpoints.
    err = _scan_target_error(local_candidate.resolve(), reports_root)
    if err is not None:
        return jsonify_error(err)
    return None


def _create_project_error_response(result) -> tuple[Response, int] | None:
    """Map a non-success ActionProvider.create_project result to an error
    response. Returns None for a successful result (caller handles that)."""
    if result.status == CreateProjectStatus.DUPLICATE:
        return (
            jsonify({
                "error": "Project already exists",
                "code": CODE_PROJECT_EXISTS,
                "existingProjectId": result.existing_project_id,
            }),
            HTTPStatus.CONFLICT,
        )
    if result.status == CreateProjectStatus.INVALID_REPO:
        return json_error(result.message, HTTPStatus.BAD_REQUEST, CODE_INVALID_REPO)
    if result.status == CreateProjectStatus.CLONE_FAILED:
        code, status = clone_code_for(result.clone_error_kind)
        body = {"error": result.message, "code": code, "detail": output_tail(result.clone_stderr)}
        return jsonify(body), status
    return None


def _resolve_create_project_source(parsed):
    """Settle where the new project's checkout comes from.

    Returns ``(clone_dest, None)`` once the request's repo is usable, or
    ``(None, error_response)`` when it is not. URL repos need a destination
    to clone into; local repos need a path that is not inside the reports
    root.
    """
    if parsed.is_url:
        return _resolve_create_project_clone_dest(parsed.ephemeral, parsed.clone_dest)
    local_err = _validate_local_create_project_repo(parsed.repo, parsed.reports_root)
    return (parsed.clone_dest, None) if local_err is None else (None, local_err)


def handle_create_project(provider: ActionProvider) -> Response | tuple[Response, int]:
    """Register a new project (clone + scan) without starting an evaluation.

    Body: ``{ repo, cloneDest?, ephemeral?, branch?, scopePath?, discipline? }``

    A URL repo with ``ephemeral`` false answers 202 and runs the clone and scan
    as the background job reported by ``GET /api/projects/clone-status``.
    ``cloneDest`` is optional there: absent, it defaults to
    ``default_clone_root()``, created on demand and trusted wherever it is
    configured (QUODEQ_REPOS_DIR may sit outside home); a cloneDest the
    request sends must sit under the home folder. Local paths and ``ephemeral: true`` stay synchronous (200, or the
    usual 4xx/409 codes); for a local path ``cloneDest`` and ``ephemeral`` are
    ignored.
    """
    body = optional_json_object_or_response(CODE_INVALID_INPUT)
    if not isinstance(body, dict):
        return body
    parsed, error = _parse_create_project_request(body)
    if error is not None:
        return error

    clone_dest, error = _resolve_create_project_source(parsed)
    if error is not None:
        return error

    git_env, clone_url = None, None
    if parsed.is_url:
        access = resolve_access(parsed.repo)
        if not access.reachable:
            return access_failure_response(access)
        if not parsed.ephemeral:
            return start_clone_job(provider, parsed, clone_dest, access)
        git_env, clone_url = access.env, access.clone_url

    spec = NewProjectSpec(
        repo=parsed.repo, discipline=parsed.discipline, scope_path=parsed.scope_path,
        clone_dest=clone_dest, ephemeral=parsed.ephemeral, git_env=git_env, clone_url=clone_url,
    )
    result = provider.create_project(parsed.reports_root, spec)
    if result.status == CreateProjectStatus.CLONE_FAILED:
        forget_url(parsed.repo)  # a stale "reachable" cache entry must not outlive a failed clone

    error = _create_project_error_response(result)
    if error is not None:
        return error

    # The 5s ProjectsCache would otherwise hide the new project from an
    # immediately-following GET /api/projects (the wizard refetches the
    # list as soon as it closes).
    provider.invalidate_projects_cache()
    return jsonify({"projectId": result.project_id, "scanData": result.scan_data})
