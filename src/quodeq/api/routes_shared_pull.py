"""Pull-a-shared-project-locally route.

This is a deliberate, spec-approved exception to the read-only invariant
documented in routes_shared.py's module docstring: it mutates LOCAL state
(the local reports directory, via import_zip_stream), not the shared
repository clone itself. The clone is only read from to build the
in-memory zip. It is therefore intentionally included in the
allowed-mutations set of the read-only sweep test
(tests/api/test_routes_shared_read.py::test_no_mutating_routes_under_shared).
"""
from __future__ import annotations

import zipfile
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api._constants import CODE_INVALID_ACTION, CODE_NOT_FOUND
from quodeq.api.helpers import json_error, optional_json_object_or_response, validate_segment
from quodeq.api.import_project import IMPORT_LOG
from quodeq.api.zip import build_project_zip
from quodeq.services.base import ActionProvider
from quodeq.services.project_archive_export import ExportSizeLimitError
from quodeq.services.project_import import IMPORT_ACTIONS, import_zip_stream
from quodeq.services.shared_repo import clone_lock
from quodeq.services.shared_pull_job import (
    CODE_PULL_FAILED,
    PullOutcome,
    PullStartResult,
    start_pull,
)

from .routes_common import reports_dir
from .routes_shared_common import logger, shared_project_dir, with_shared_root

CODE_PULL_IN_PROGRESS = "PULL_IN_PROGRESS"
CODE_PULL_START_FAILED = "PULL_START_FAILED"
CODE_PULL_TOO_LARGE = "PULL_TOO_LARGE"


def _build_pull_zip(project: str, project_path: Path) -> tuple[Path, None] | tuple[None, PullOutcome]:
    """Build the zip of the shared project. Returns (zip_path, None) on
    success, (None, failed outcome) on failure."""
    try:
        return build_project_zip(project_path), None
    except ExportSizeLimitError as exc:
        # public_message is the service's fixed text (limits and the env var), never str(exc).
        return None, PullOutcome(False, code=CODE_PULL_TOO_LARGE, error=exc.public_message)
    except (OSError, zipfile.BadZipFile, ValueError):
        logger.exception("Failed to build zip for shared pull of %s", project)
        return None, PullOutcome(
            False, code="EXPORT_ERROR", error="Failed to build project archive from the shared repository",
        )


def _outcome_from_import(status: int, body: dict, project: str) -> PullOutcome:
    if status == HTTPStatus.OK:
        return PullOutcome(True, body.get("projectId"), body.get("projectName"), bool(body.get("renamed")))
    return PullOutcome(
        False, code=body.get("code") or CODE_PULL_FAILED, error=body.get("error"),
        conflict_kind=body.get("kind"), source_project_id=body.get("sourceProjectId") or project,
    )


def _import_pulled_zip(
    project: str, zip_path: Path, action: str | None, remote_addr: str | None, reports: str,
) -> PullOutcome:
    try:
        with zip_path.open("rb") as stream:
            outcome = import_zip_stream(stream, reports, action, remote_addr=remote_addr, log=IMPORT_LOG)
        return _outcome_from_import(outcome.status, outcome.body, project)
    except OSError:
        logger.exception("Failed to read zip for shared pull of %s", project)
        return PullOutcome(
            False, code="EXPORT_ERROR", error="Failed to read project archive from the shared repository",
        )
    finally:
        try:
            zip_path.unlink()
        except OSError as exc:
            logger.warning("Failed to remove temp zip %s: %s", zip_path, exc)


def _pull_outcome(
    project: str, project_path: Path, url: str, action: str | None, remote_addr: str | None, reports: str,
) -> PullOutcome:
    """The job body: zip the shared project (under the clone lock) and import it locally."""
    with clone_lock(url):  # a refresh may rewrite the clone; only the zip build reads it
        zip_path, failure = _build_pull_zip(project, project_path)
    if failure is not None:
        return failure
    return _import_pulled_zip(project, zip_path, action, remote_addr, reports)


def handle_shared_pull(provider: ActionProvider, project: str, eval_root: Path, url: str) -> Response | tuple[Response, int]:
    """Handle POST /api/shared/projects/<project>/pull: validate, then start the pull job."""
    err = validate_segment(project)
    if err:
        return err
    project_path = shared_project_dir(eval_root, project)
    if project_path is None:
        return json_error(
            "Project not found in the shared repository", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND,
        )

    payload = optional_json_object_or_response(CODE_INVALID_ACTION)
    if not isinstance(payload, dict):
        return payload
    action = payload.get("action")
    if action is not None and not isinstance(action, str):
        return json_error("action must be a string", HTTPStatus.BAD_REQUEST, CODE_INVALID_ACTION)
    if action is not None and action not in IMPORT_ACTIONS:
        return json_error("action must be copy or replace", HTTPStatus.BAD_REQUEST, CODE_INVALID_ACTION)
    # The job thread has no Flask request context or app state, so read them here.
    remote_addr = request.remote_addr
    reports = reports_dir()
    outcome = start_pull(
        project,
        pull=lambda p: _pull_outcome(p, project_path, url, action, remote_addr, reports),
        on_done=provider.invalidate_projects_cache,
        log=IMPORT_LOG,
    )
    if outcome == PullStartResult.ALREADY_RUNNING:
        return json_error("a pull is already running", HTTPStatus.CONFLICT, CODE_PULL_IN_PROGRESS)
    if outcome != PullStartResult.STARTED:
        return json_error(
            "could not start the pull job, see server logs",
            HTTPStatus.INTERNAL_SERVER_ERROR, CODE_PULL_START_FAILED,
        )
    return jsonify({"started": True, "project": project}), HTTPStatus.ACCEPTED


def register_shared_pull_routes(app: Flask, provider: ActionProvider) -> None:
    """Bind POST /api/shared/projects/<project>/pull, which copies a shared project local.

    Answers 202 and runs the zip and import as a background job; the outcome
    (``projectId``, ``projectName``, ``renamed`` or a ``code``) is reported
    under ``pull`` in GET /api/shared/status.

    Body ``{"action": "copy"|"replace"}`` resolves a ``PROJECT_EXISTS``
    collision from a previous attempt, as for the manual import route.
    """

    def shared_pull(project: str, eval_root: Path, url: str) -> Response | tuple[Response, int]:
        return handle_shared_pull(provider, project, eval_root, url)

    app.post("/api/shared/projects/<project>/pull")(with_shared_root(shared_pull))
