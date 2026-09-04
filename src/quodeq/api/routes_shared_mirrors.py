"""Read-only mirrors of the project read endpoints, scoped to the shared clone.

Split out of routes_shared.py (Task 9). Each route below delegates to the
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

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.services import _fs_projects, _fs_reports
from quodeq.services.compare import build_compare_summary
from quodeq.services._runs_unit import build_runs_unit
from quodeq.services.dismissed import load_dismissed
from quodeq.services.scoring import get_project_scores, get_scores_slim
from quodeq.services.shared_repo import (
    published_meta,
    last_synced_at,
    shared_index_db_path,
)
from quodeq.services.verified import verified_entries
from quodeq.shared.serialization import to_camel_dict

from .routes_shared_common import _logger, _shared_project_dir, _validate_segment, _with_shared_root

# Mirrors quodeq.api.routes_findings._MAX_DISMISSED_LIMIT — the shared
# dismissed-findings mirror clamps to the same hard cap as the local route.
_MAX_DISMISSED_LIMIT = 5000


def register_shared_mirror_routes(app: Flask) -> None:
    # refresh_shared_clone and sync_shared_index are looked up on the
    # quodeq.api.routes_shared facade at call time (rather than imported
    # directly here) so that tests patching
    # "quodeq.api.routes_shared.refresh_shared_clone" /
    # "...sync_shared_index" keep working after the split.
    from quodeq.api import routes_shared as _routes_shared

    @app.get("/api/shared/projects")
    @_with_shared_root
    def shared_projects(eval_root: Path, url: str):
        stale = None
        if request.args.get("refresh") == "1":
            # Refresh-on-read: the UI calls this on tab entry to force the
            # clone up to date before listing, rather than showing whatever
            # was last fetched. A failed refresh (host unreachable) is not
            # fatal -- fall through and serve the existing (now-stale)
            # clone contents, just flag it. The index is only re-synced
            # after a successful refresh; there is nothing new to index
            # when the fetch itself failed.
            ok, _ = _routes_shared.refresh_shared_clone(url)
            if ok:
                _routes_shared.sync_shared_index(url)
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
        projects = _fs_projects.build_project_list(
            eval_root, backfill=False, inline_summaries=True,
        )
        listing = {"projects": [to_camel_dict(p) for p in projects]}
        meta = published_meta(url)
        for project in listing["projects"]:
            key = project.get("id") or project.get("name")
            project.update(meta.get(key, {}))
            project["source"] = "shared"
        listing["lastSynced"] = last_synced_at(url)
        if stale is not None:
            listing["stale"] = stale
        return jsonify(listing)

    @app.get("/api/shared/projects/<project>/info")
    @_with_shared_root
    def shared_project_info(project: str, eval_root: Path, url: str):
        err = _validate_segment(project)
        if err:
            return err
        info = _fs_projects.get_project_info(str(eval_root), project)
        if not info:
            body, status = error_response("Project info not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        # Same publishedBy/publishedAt enrichment as the list route
        # (shared_projects above) -- without it the UI's shared-project hero
        # badge has no "published by <name>" to show. `project` here is the
        # directory name under the clone root, the exact key published_meta
        # indexes by.
        meta = published_meta(url)
        info.update(meta.get(project, {}))
        info["source"] = "shared"
        return jsonify(info)

    @app.get("/api/shared/projects/<project>/runs")
    @_with_shared_root
    def shared_runs(project: str, eval_root: Path, url: str):
        err = _validate_segment(project)
        if err:
            return err
        try:
            runs = build_runs_unit(eval_root, shared_index_db_path(url), project)
        except Exception:
            _logger.exception("Failed to build shared runs unit for %s", project)
            body, status = error_response("Failed to load runs", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")
            return jsonify(body), status
        return jsonify({"runs": runs})

    @app.get("/api/shared/projects/<project>/dashboard")
    @_with_shared_root
    def shared_dashboard(project: str, eval_root: Path, url: str):
        err = _validate_segment(project)
        if err:
            return err
        run = request.args.get("run", "latest")
        try:
            payload = _fs_reports.get_dashboard(str(eval_root), project, run)
        except FileNotFoundError:
            body, status = error_response("Dashboard data not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(payload)

    @app.get("/api/shared/projects/<project>/accumulated")
    @_with_shared_root
    def shared_accumulated(project: str, eval_root: Path, url: str):
        err = _validate_segment(project)
        if err:
            return err
        as_of = request.args.get("asOf")
        payload = _fs_reports.get_accumulated(str(eval_root), project, as_of)
        if payload is None:
            body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(payload)

    @app.get("/api/shared/projects/<project>/scores")
    @_with_shared_root
    def shared_scores(project: str, eval_root: Path, url: str):
        err = _validate_segment(project)
        if err:
            return err
        as_of = request.args.get("asOf")
        try:
            result = get_project_scores(eval_root, project, as_of)
        except Exception:
            _logger.exception("Unexpected error fetching shared scores for project %s", project)
            body, status = error_response("Failed to load scores", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")
            return jsonify(body), status
        if result is None:
            body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(result)

    @app.get("/api/shared/projects/<project>/compare-summary")
    @_with_shared_root
    def shared_compare_summary(project: str, eval_root: Path, url: str):
        err = _validate_segment(project)
        if err:
            return err
        try:
            result = build_compare_summary(eval_root, project)
        except Exception:
            _logger.exception("Unexpected error building shared compare summary for project %s", project)
            body, status = error_response("Failed to load compare summary", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")
            return jsonify(body), status
        if result is None:
            body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(result)

    @app.get("/api/shared/projects/<project>/scores/<run_id>")
    @_with_shared_root
    def shared_run_scores(project: str, run_id: str, eval_root: Path, url: str):
        err = _validate_segment(project, run_id)
        if err:
            return err
        try:
            result = get_scores_slim(eval_root, project, run_id)
        except FileNotFoundError:
            body, status = error_response("Run not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(result)

    @app.get("/api/shared/projects/<project>/dimensions/<dim>/eval")
    @_with_shared_root
    def shared_dimension_eval(project: str, dim: str, eval_root: Path, url: str):
        run_id = request.args.get("run", "latest")
        err = _validate_segment(project, dim, run_id)
        if err:
            return err
        payload = _fs_reports.get_dimension_eval(str(eval_root), project, run_id, dim)
        if payload is None:
            body, status = error_response("Eval file not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        if payload.get("waiting"):
            return jsonify(payload), HTTPStatus.ACCEPTED
        return jsonify(payload)

    @app.get("/api/shared/projects/<project>/violations")
    @_with_shared_root
    def shared_violations(project: str, eval_root: Path, url: str):
        run_id = request.args.get("run", "latest")
        err = _validate_segment(project, run_id)
        if err:
            return err
        try:
            payload = _fs_reports.get_violations(str(eval_root), project, run_id)
        except FileNotFoundError:
            body, status = error_response("Violation data not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(to_camel_dict(payload))

    # The local routes take ``project`` as a query param
    # (``/api/findings/dismissed?project=``) since /api/findings/* is a flat
    # namespace shared by mutation routes too. Every other shared mirror
    # nests ``project`` as a URL path segment, so these two follow that
    # convention instead of the local route's exact URL shape -- the response
    # bodies (bare JSON array, same item shape) are unchanged.
    @app.get("/api/shared/projects/<project>/findings/dismissed")
    @_with_shared_root
    def shared_dismissed_findings(project: str, eval_root: Path, url: str):
        err = _validate_segment(project)
        if err:
            return err
        project_dir = _shared_project_dir(eval_root, project)
        if project_dir is None:
            return jsonify([])
        raw_limit = request.args.get("limit", _MAX_DISMISSED_LIMIT, type=int)
        limit = max(1, min(raw_limit, _MAX_DISMISSED_LIMIT))
        offset = max(0, request.args.get("offset", 0, type=int))
        items = load_dismissed(project_dir, offset=offset, limit=limit)
        return jsonify(items)

    @app.get("/api/shared/projects/<project>/findings/verified")
    @_with_shared_root
    def shared_verified_findings(project: str, eval_root: Path, url: str):
        err = _validate_segment(project)
        if err:
            return err
        project_dir = _shared_project_dir(eval_root, project)
        if project_dir is None:
            return jsonify([])
        raw_limit = request.args.get("limit", _MAX_DISMISSED_LIMIT, type=int)
        limit = max(1, min(raw_limit, _MAX_DISMISSED_LIMIT))
        offset = max(0, request.args.get("offset", 0, type=int))
        items = verified_entries(project_dir, offset=offset, limit=limit)
        return jsonify(items)
