"""POST /api/projects as a background job for a git URL, and the job's status route.

``handle_create_project`` hands a non-ephemeral URL repo here: the clone and
scan run on a daemon thread behind the single ``clone`` slot while the route
answers 202. The thread touches no Flask context; everything it needs is
captured from the request first.
"""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

from flask import Flask, Response, jsonify

from quodeq.api._constants import CODE_INVALID_INPUT, CODE_INVALID_REPO, CODE_PROJECT_EXISTS
from quodeq.api.helpers import json_error
from quodeq.api.routes_common import sync_block
from quodeq.services.base import ActionProvider, CreateProjectResult, CreateProjectStatus, NewProjectSpec
from quodeq.services.clone_codes import clone_code_for
from quodeq.services.github_access import AccessResult, forget_url
from quodeq.services.project_clone_job import (
    CODE_CLONE_IN_PROGRESS, CODE_CLONE_START_FAILED, MESSAGE_CLONE_START_FAILED, CloneHooks, CloneOutcome, CloneStartResult,
    get_clone_status, start_clone,
)
from quodeq.shared.git_errors import output_tail
from quodeq.shared.log_sink import SHARED_LOG
from quodeq.shared.repo import project_name_from_repo

if TYPE_CHECKING:
    from quodeq.api.routes_project_create import CreateProjectRequest

MESSAGE_CLONE_IN_PROGRESS = "a clone is already running"


def _outcome_from_result(repo: str, result: CreateProjectResult) -> CloneOutcome:
    """Translate a create-project result into the job's outcome (a coded failure or the project)."""
    if result.status == CreateProjectStatus.CREATED:
        return CloneOutcome(
            True, project_id=result.project_id, project_name=project_name_from_repo(repo),
            scan_data=result.scan_data,
        )
    if result.status == CreateProjectStatus.DUPLICATE:
        # The UI resumes the existing project from ``detail``.
        return CloneOutcome(False, error=result.message, code=CODE_PROJECT_EXISTS, detail=result.existing_project_id or "")
    if result.status == CreateProjectStatus.INVALID_REPO:
        return CloneOutcome(False, error=result.message, code=CODE_INVALID_REPO)
    if result.status == CreateProjectStatus.CLONE_FAILED:
        forget_url(repo)  # a stale "reachable" cache entry must not outlive a failed clone
        code, _status = clone_code_for(result.clone_error_kind)
        return CloneOutcome(False, error=result.message, code=code, detail=output_tail(result.clone_stderr))
    return CloneOutcome(False, error=result.message, code=CODE_INVALID_INPUT)


def start_clone_job(
    provider: ActionProvider, parsed: CreateProjectRequest, clone_dest: str, access: AccessResult,
) -> tuple[Response, int]:
    """Start the clone+scan as the background job; 202, or 409 / 500 when it cannot start."""
    dest = str(Path(clone_dest) / project_name_from_repo(parsed.repo))

    def create(progress, on_phase) -> CloneOutcome:
        spec = NewProjectSpec(
            repo=parsed.repo, discipline=parsed.discipline, scope_path=parsed.scope_path,
            clone_dest=clone_dest, ephemeral=False, git_env=access.env, clone_url=access.clone_url,
            progress=progress, on_phase=on_phase,
        )
        return _outcome_from_result(parsed.repo, provider.create_project(parsed.reports_root, spec))

    outcome = start_clone(
        parsed.repo, dest, hooks=CloneHooks(create, on_done=provider.invalidate_projects_cache), log=SHARED_LOG,
    )
    if outcome is CloneStartResult.ALREADY_RUNNING:
        return json_error(MESSAGE_CLONE_IN_PROGRESS, HTTPStatus.CONFLICT, CODE_CLONE_IN_PROGRESS)
    if outcome is not CloneStartResult.STARTED:
        return json_error(MESSAGE_CLONE_START_FAILED, HTTPStatus.INTERNAL_SERVER_ERROR, CODE_CLONE_START_FAILED)
    return jsonify({"started": True, "repo": parsed.repo, "dest": dest}), HTTPStatus.ACCEPTED


def register_project_clone_routes(app: Flask) -> None:
    """Register GET /api/projects/clone-status."""

    @app.get("/api/projects/clone-status")
    def clone_status() -> Response:
        """The add-project job's slot: state, phase, percent, and the created project."""
        return jsonify(sync_block(get_clone_status()))
