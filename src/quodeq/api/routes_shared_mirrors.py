"""Read-only mirrors of the project read endpoints, scoped to the shared clone.

Split out of routes_shared.py. Each route below delegates to the
SAME service function its local counterpart uses (see
api/routes_project_list.py, routes_project_data.py, _scores_routes.py,
routes_runs.py, routes_findings.py), with the shared clone's evaluations
root standing in for the local reports directory. The response shape is
therefore identical to the local route's; only the data source differs.

Read-only invariant: no finding-mutation routes exist in this module or
anywhere under /api/shared/*, per routes_shared.py's module docstring.
"""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Callable

from flask import Flask, Response, jsonify, request

from quodeq.api._constants import CODE_NOT_FOUND, QUERY_FLAG_TRUE_NUMERIC
from quodeq.api.helpers import json_error
from quodeq.api.routes_shared_findings_mirrors import register_shared_findings_mirror_routes
from quodeq.core.types.project_source import ProjectSource
from quodeq.services import fs_reports, fs_projects
from quodeq.services.compare import build_compare_summary
from quodeq.services.run_constants import LATEST_RUN
from quodeq.services.runs_unit import build_runs_unit
from quodeq.services.scoring import get_project_scores, get_scores_slim
from quodeq.services.shared_repo import (
    published_meta,
    last_synced_at,
    shared_index_db_path,
)
from quodeq.shared.log_sink import SHARED_LOG
from quodeq.shared.serialization import to_camel_dict

from .routes_shared_common import logger, validate_segment, with_shared_root

_PROJECT_NOT_FOUND = "Project not found"  # repeated across the shared-mirror read routes


def _shared_projects(
    eval_root: Path, url: str,
    refresh_clone: Callable[[str], tuple[bool, object]], sync_index: Callable[[str], object],
):
    stale = None
    if request.args.get("refresh") == QUERY_FLAG_TRUE_NUMERIC:
        # Refresh-on-read: the UI calls this on tab entry to force the
        # clone up to date before listing, rather than showing whatever
        # was last fetched. A failed refresh (host unreachable) is not
        # fatal -- fall through and serve the existing (now-stale)
        # clone contents, just flag it. The index is only re-synced
        # after a successful refresh; there is nothing new to index
        # when the fetch itself failed.
        ok, _ = refresh_clone(url)
        if ok:
            sync_index(url)
            stale = False
        else:
            stale = True
    # backfill=False: the shared clone is a git worktree, not a local
    # evaluations dir -- writing onboardingCompletedAt into
    # repository_info.json here would dirty it, and a dirty worktree can
    # make publish's `pull --rebase` refuse (confusing wedge) the next
    # time someone publishes into this clone.
    # inline_summaries=True: this route has no warm-up engine to fill a
    # missing project-card summary later, so a cache miss must compute
    # it inline here instead of reporting it pending forever.
    projects = fs_projects.build_project_list(
        eval_root, backfill=False, inline_summaries=True,
    )
    listing = {"projects": [to_camel_dict(p) for p in projects]}
    meta = published_meta(url)
    for project in listing["projects"]:
        key = project.get("id") or project.get("name")
        project.update(meta.get(key, {}))
        project["source"] = ProjectSource.SHARED
    listing["lastSynced"] = last_synced_at(url)
    if stale is not None:
        listing["stale"] = stale
    return jsonify(listing)


def _load_or_500(
    load: Callable[[], object], project: str, *, log_msg: str, error_msg: str,
) -> tuple[object, tuple[Response, int] | None]:
    """``(result, None)`` from *load*, or ``(None, 500 response)`` when it raises."""
    try:
        return load(), None
    except Exception:
        logger.exception(log_msg, project)
        return None, json_error(error_msg, HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")


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
    meta = published_meta(url)
    info.update(meta.get(project, {}))
    info["source"] = ProjectSource.SHARED
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
    payload = fs_reports.get_dimension_eval(str(eval_root), project, run_id, dim)
    if payload is None:
        return json_error("Eval file not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
    if payload.get("waiting"):
        return jsonify(payload), HTTPStatus.ACCEPTED
    return jsonify(payload)


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
    # refresh_shared_clone and sync_shared_index are looked up on the
    # quodeq.api.routes_shared facade at call time (rather than imported
    # directly here) so that tests patching
    # "quodeq.api.routes_shared.refresh_shared_clone" /
    # "...sync_shared_index" keep working after the split.
    from quodeq.api import routes_shared as _routes_shared

    @app.get("/api/shared/projects")
    @with_shared_root
    def shared_projects(eval_root: Path, url: str):
        return _shared_projects(
            eval_root, url, _routes_shared.refresh_shared_clone, _routes_shared.sync_shared_index,
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
