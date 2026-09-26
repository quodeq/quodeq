"""Read-only mirrors of the project read endpoints, scoped to the shared clone.

Each route below delegates to the SAME service function its local
counterpart uses (see api/routes_project_list.py, routes_project_data.py,
_scores_routes.py, routes_runs.py, routes_findings.py), with the shared
clone's evaluations root standing in for the local reports directory. The
response shape is therefore identical to the local route's; only the data
source differs.

Read-only invariant: no finding-mutation routes exist in this module or
anywhere under /api/shared/*, per routes_shared.py's module docstring.

``refresh_shared_clone`` and ``sync_shared_index`` are imported directly
from their real owner, never through the ``routes_shared`` facade, so this
module never imports back a sibling that imports it. Tests patch
"quodeq.api.routes_shared_mirrors.refresh_shared_clone" /
"...sync_shared_index".
"""
from __future__ import annotations

import sqlite3
from http import HTTPStatus
from pathlib import Path
from typing import Callable

from flask import Flask, Response, current_app, jsonify, request

from quodeq.api._constants import CODE_INTERNAL_ERROR, CODE_NOT_FOUND, QUERY_FLAG_TRUE_NUMERIC
from quodeq.api.helpers import dimension_eval_response, json_error, validate_segment
from quodeq.api.routes_shared_findings_mirrors import register_shared_findings_mirror_routes
from quodeq.services import fs_reports, fs_projects
from quodeq.services.compare import build_compare_summary
from quodeq.services.run_constants import LATEST_RUN
from quodeq.services.runs_unit import build_runs_unit
from quodeq.services.scoring import get_project_scores, get_scores_slim
from quodeq.services.shared_listing import enrich_shared_info, list_shared_projects
from quodeq.services.shared_repo import (
    refresh_shared_clone,
    shared_index_db_path,
    sync_shared_index,
)
from quodeq.shared.log_sink import SHARED_LOG
from quodeq.shared.serialization import to_camel_dict

from .routes_shared_common import logger, with_shared_root

_PROJECT_NOT_FOUND = "Project not found"  # repeated across the shared-mirror read routes


def _shared_projects(
    eval_root: Path, url: str,
    refresh_clone: Callable[[str], tuple[bool, object]], sync_index: Callable[[str], object],
):
    listing = list_shared_projects(
        eval_root, url,
        refresh=request.args.get("refresh") == QUERY_FLAG_TRUE_NUMERIC,
        refresh_clone=refresh_clone, sync_index=sync_index,
        serialize=to_camel_dict,
    )
    return jsonify(listing)


def _load_or_500(
    load: Callable[[], object], project: str, *, log_msg: str, error_msg: str,
) -> tuple[object, tuple[Response, int] | None]:
    """``(result, None)`` from *load*, or ``(None, 500 response)`` when it raises."""
    try:
        return load(), None
    except (OSError, sqlite3.Error, ValueError):
        logger.exception(log_msg, project)
        return None, json_error(error_msg, HTTPStatus.INTERNAL_SERVER_ERROR, CODE_INTERNAL_ERROR)


@with_shared_root
def shared_project_info(project: str, eval_root: Path, url: str):
    """Return the shared clone's project card, enriched with who published it.

    The publishedBy/publishedAt fields have no local counterpart; the UI's
    shared-project hero badge needs them.
    """
    err = validate_segment(project)
    if err:
        return err
    info, err = _load_or_500(
        lambda: fs_projects.get_project_info(str(eval_root), project), project,
        log_msg="Failed to load shared project info for %s", error_msg="Failed to load project info",
    )
    if err:
        return err
    if not info:
        return json_error("Project info not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
    # Same publishedBy/publishedAt enrichment as the list route
    # (shared_projects above) -- without it the UI's shared-project hero
    # badge has no "published by <name>" to show. `project` here is the
    # directory name under the clone root, the exact key published_meta
    # indexes by.
    enrich_shared_info(info, project, url)
    return jsonify(info)


@with_shared_root
def shared_runs(project: str, eval_root: Path, url: str):
    """Return the shared clone's run history for a project, for the run picker."""
    err = validate_segment(project)
    if err:
        return err
    runs, err = _load_or_500(
        lambda: build_runs_unit(eval_root, shared_index_db_path(url), project), project,
        log_msg="Failed to build shared runs unit for %s", error_msg="Failed to load runs",
    )
    if err:
        return err
    return jsonify({"runs": runs})


@with_shared_root
def shared_dashboard(project: str, eval_root: Path):
    """Return one run's dashboard payload from the shared clone. ``?run=`` defaults to latest."""
    err = validate_segment(project)
    if err:
        return err
    run = request.args.get("run", LATEST_RUN)
    try:
        payload = fs_reports.get_dashboard(str(eval_root), project, run, log=SHARED_LOG)
    except FileNotFoundError:
        return json_error("Dashboard data not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
    return jsonify(payload)


@with_shared_root
def shared_accumulated(project: str, eval_root: Path):
    """Return the shared clone's accumulated-score history, optionally cut at ``?asOf=``."""
    err = validate_segment(project)
    if err:
        return err
    as_of = request.args.get("asOf")
    payload = fs_reports.get_accumulated(str(eval_root), project, as_of, log=SHARED_LOG)
    if payload is None:
        return json_error(_PROJECT_NOT_FOUND, HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
    return jsonify(payload)


@with_shared_root
def shared_scores(project: str, eval_root: Path):
    """Return the shared clone's per-dimension scores, optionally cut at ``?asOf=``."""
    err = validate_segment(project)
    if err:
        return err
    as_of = request.args.get("asOf")
    result, err = _load_or_500(
        lambda: get_project_scores(eval_root, project, as_of), project,
        log_msg="Unexpected error fetching shared scores for project %s", error_msg="Failed to load scores",
    )
    if err:
        return err
    if result is None:
        return json_error(_PROJECT_NOT_FOUND, HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
    return jsonify(result)


@with_shared_root
def shared_compare_summary(project: str, eval_root: Path):
    """Return the run-over-run comparison for a shared project, for the compare view."""
    err = validate_segment(project)
    if err:
        return err
    result, err = _load_or_500(
        lambda: build_compare_summary(eval_root, project), project,
        log_msg="Unexpected error building shared compare summary for project %s",
        error_msg="Failed to load compare summary",
    )
    if err:
        return err
    if result is None:
        return json_error(_PROJECT_NOT_FOUND, HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
    return jsonify(result)


@with_shared_root
def shared_run_scores(project: str, run_id: str, eval_root: Path):
    """Return one shared run's scores in the slim shape the run picker renders."""
    err = validate_segment(project, run_id)
    if err:
        return err
    try:
        result = get_scores_slim(eval_root, project, run_id)
    except FileNotFoundError:
        return json_error("Run not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
    return jsonify(result)


@with_shared_root
def shared_dimension_eval(project: str, dim: str, eval_root: Path):
    """Return one dimension's evaluation from the shared clone.

    202 with ``waiting`` set when the dimension is still being written, so the
    UI polls instead of showing an error.
    """
    run_id = request.args.get("run", LATEST_RUN)
    err = validate_segment(project, dim, run_id)
    if err:
        return err
    evaluators_dir = current_app.config.get("STANDARDS_EVALUATORS_DIR")
    return dimension_eval_response(fs_reports.get_dimension_eval(
        str(eval_root), project, run_id, dim,
        evaluators_dir=Path(evaluators_dir) if evaluators_dir else None,
    ))


@with_shared_root
def shared_violations(project: str, eval_root: Path):
    """Return one shared run's violations, camelCased for the UI."""
    run_id = request.args.get("run", LATEST_RUN)
    err = validate_segment(project, run_id)
    if err:
        return err
    try:
        payload = fs_reports.get_violations(str(eval_root), project, run_id, log=SHARED_LOG)
    except FileNotFoundError:
        return json_error("Violation data not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
    return jsonify(to_camel_dict(payload))


def register_shared_mirror_routes(app: Flask) -> None:
    """Bind every /api/shared/* read mirror, including the findings listings.

    Called from routes_shared.py, which owns the read-only invariant for the
    whole /api/shared/* namespace.
    """
    @app.get("/api/shared/projects")
    @with_shared_root
    def shared_projects(eval_root: Path, url: str):
        return _shared_projects(
            eval_root, url, refresh_shared_clone, sync_shared_index,
        )

    app.get("/api/shared/projects/<project>/info")(shared_project_info)
    app.get("/api/shared/projects/<project>/runs")(shared_runs)
    app.get("/api/shared/projects/<project>/dashboard")(shared_dashboard)
    app.get("/api/shared/projects/<project>/accumulated")(shared_accumulated)
    app.get("/api/shared/projects/<project>/scores")(shared_scores)
    app.get("/api/shared/projects/<project>/compare-summary")(shared_compare_summary)
    app.get("/api/shared/projects/<project>/scores/<run_id>")(shared_run_scores)
    app.get("/api/shared/projects/<project>/dimensions/<dim>/eval")(shared_dimension_eval)
    app.get("/api/shared/projects/<project>/violations")(shared_violations)
    register_shared_findings_mirror_routes(app)
