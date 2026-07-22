"""Routes for the shared results repository (config, status, refresh, publish),
plus read-only mirrors of the project read endpoints scoped to the shared clone.

Read-only invariant: no finding-mutation routes exist in this module or
anywhere under /api/shared/*. Every ``/api/shared/projects/...`` route is a
thin GET-only delegation to the same service functions the local
``/api/projects/...`` routes use, pointed at the shared clone's evaluations
root (via ``_with_shared_root``) instead of the local reports directory.
"""
from __future__ import annotations

import functools
import logging
import shutil
import zipfile
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.api.import_project import import_zip_stream
from quodeq.api.zip import _build_project_zip
from quodeq.core.types import to_camel_dict
from quodeq.services import _fs_projects, _fs_reports
from quodeq.services._runs_unit import build_runs_unit
from quodeq.services.dismissed import load_dismissed
from quodeq.services.score_cache import score_cache_path_override
from quodeq.services.scoring import get_project_scores, get_scores_slim
from quodeq.services.shared_publish import get_publish_status, start_publish
from quodeq.services.shared_repo import (
    check_repo_format,
    ensure_shared_clone,
    last_synced_at,
    published_meta,
    read_state,
    refresh_shared_clone,
    shared_cache_dir,
    shared_evaluations_root,
    shared_index_db_path,
    shared_score_cache_path,
    sync_shared_index,
    validate_remote_url,
)
from quodeq.services.shared_settings import (
    SharedSettings,
    read_settings,
    write_settings,
)
from quodeq.services.verified import verified_entries
from quodeq.shared.validation import validate_path_segment

from .routes_common import reports_dir

_logger = logging.getLogger(__name__)

# Mirrors quodeq.api.routes_findings._MAX_DISMISSED_LIMIT — the shared
# dismissed-findings mirror clamps to the same hard cap as the local route.
_MAX_DISMISSED_LIMIT = 5000


def _with_shared_root(fn):
    """Resolve the configured clone; inject eval_root; scope the score cache.

    Every decorated route becomes: 409 when unconfigured, 409 when the
    clone's format is foreign or newer than this build understands, 503 when
    the clone hasn't been fetched yet at all, else the wrapped view runs with
    ``eval_root`` (the shared clone's evaluations directory) and ``url`` (the
    configured remote) injected as keyword arguments, with the score cache
    transparently scoped to this clone's own cache DB (Task 9) so its rows
    never mix with the local clone's cache.

    "ok" and "empty" (cloned, never published into) both proceed: an empty
    clone is a legitimate first-connect state, not an error, and every
    wrapped list-shaped route already tolerates a missing evaluations dir by
    returning an empty result (see build_project_list) rather than raising.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        settings = read_settings()
        if not settings.url:
            return jsonify({"error": "no shared repository configured"}), 409
        state = read_state(settings.url)
        if state == "unsupported_version":
            return (
                jsonify({"error": "this shared repository requires a newer version of quodeq"}),
                409,
            )
        if state == "foreign":
            return (
                jsonify(
                    {
                        "error": "the configured repository does not look like a quodeq results repository",
                        "code": "FOREIGN_REPO",
                    }
                ),
                409,
            )
        if state == "missing":
            return (
                jsonify(
                    {"error": "the shared repository has not been cloned yet — reconnect it in Settings"}
                ),
                503,
            )
        root = shared_evaluations_root(settings.url)
        with score_cache_path_override(shared_score_cache_path(settings.url)):
            return fn(*args, eval_root=root, url=settings.url, **kwargs)

    return wrapper


def _validate_segment(*segments: str) -> tuple[Response, int] | None:
    """Shared-route path-segment guard (Task 7 precedent).

    Every shared mirror that takes a project/run/dimension segment validates
    it here, even where the local route it mirrors relies solely on the
    service layer's own traversal check — defense in depth for a surface
    that serves a second, independently-controlled clone.
    """
    try:
        validate_path_segment(*segments)
    except ValueError:
        body, status = error_response("Invalid parameter", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
        return jsonify(body), status
    return None


def _shared_project_dir(eval_root: Path, project: str) -> Path | None:
    """Resolve *project* under *eval_root*; None if it would escape the root."""
    base = eval_root.resolve()
    resolved = (base / project).resolve()
    if not resolved.is_relative_to(base):
        return None
    return resolved


def register_shared_routes(app: Flask) -> None:
    @app.get("/api/shared/status")
    def shared_status() -> Response:
        settings = read_settings()
        synced = last_synced_at(settings.url) if settings.url else None
        # The wire shape is camelCase throughout; the publish status dict is
        # a service-internal snake_case structure, so rename at the boundary.
        publish = get_publish_status()
        publish["finishedAt"] = publish.pop("finished_at", None)
        return jsonify(
            {
                "configured": settings.url is not None,
                "url": settings.url,
                "lastSynced": synced,
                "syncing": False,
                # Reserved for sync-level failures; always present so the UI
                # can bind to it without existence checks.
                "error": None,
                "publish": publish,
                # ok | empty | foreign | unsupported_version | missing | None
                # (unconfigured) -- lets the UI distinguish "healthy but
                # never published into" from the failure states instead of
                # inferring clone health from configured+lastSynced alone.
                "repoState": read_state(settings.url) if settings.url else None,
            }
        )

    @app.put("/api/shared/config")
    def shared_config_put() -> Response | tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        url = str(body.get("url") or "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400
        try:
            validate_remote_url(url)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        # Audit finding A4: reconnecting to a URL whose cache dir is already
        # on disk (a prior connect, possibly stale) must not silently keep
        # serving whatever was last fetched -- ensure_shared_clone below
        # early-returns an existing clone without fetching, so the freshness
        # check has to happen here, before it. refresh_shared_clone acquires
        # clone_lock itself (RLock, so nesting would be safe too, but there
        # is nothing else in this route that needs the lock held around it).
        pre_existing = read_state(url) != "missing"
        repo = ensure_shared_clone(url)
        if repo is None:
            return (
                jsonify(
                    {"error": f"could not clone the repository, check that git can access {url}"}
                ),
                502,
            )
        if pre_existing:
            ok, _ = refresh_shared_clone(url)  # best effort; failure just leaves the pre-existing clone as-is, reason already logged internally
        # Format validation only makes sense once the clone actually exists,
        # so it runs AFTER ensure_shared_clone, not before -- a foreign or
        # too-new repo must never reach write_settings (that would connect
        # the UI to a repo every subsequent /api/shared/* route then 409s
        # on). "empty" (never published into) is a legitimate first-connect
        # state and is accepted here same as "ok".
        fmt = check_repo_format(repo)
        if fmt == "foreign":
            return (
                jsonify(
                    {"error": "the repository exists but does not look like a quodeq results repository"}
                ),
                400,
            )
        if fmt == "unsupported_version":
            return (
                jsonify({"error": "this shared repository requires a newer version of quodeq"}),
                400,
            )
        write_settings(SharedSettings(url=url))
        return jsonify({"configured": True, "url": url})

    @app.delete("/api/shared/config")
    def shared_config_delete() -> Response:
        # Audit finding A4: disconnecting must not leave the clone's cache
        # dir (repo + index.db + score_cache.db, all under shared_cache_dir)
        # behind on disk forever. Read the url BEFORE clearing settings (it's
        # gone from settings after write_settings), then remove it AFTER --
        # so a crash between the two leaves the (still-usable) clone in
        # place rather than an orphaned dir with no settings pointing at it.
        # ignore_errors=True: a half-removed or permission-denied cache dir
        # must not turn a disconnect into a 500.
        settings = read_settings()
        write_settings(SharedSettings(url=None))
        if settings.url is not None:
            shutil.rmtree(shared_cache_dir(settings.url), ignore_errors=True)
        return jsonify({"configured": False})

    @app.post("/api/shared/refresh")
    def shared_refresh() -> Response | tuple[Response, int]:
        settings = read_settings()
        if not settings.url:
            return jsonify({"error": "no shared repository configured"}), 400
        ok, reason = refresh_shared_clone(settings.url)
        if not ok:
            return (
                jsonify(
                    {
                        "stale": True,
                        "lastSynced": last_synced_at(settings.url),
                        "error": reason,
                    }
                ),
                502,
            )
        return jsonify({"stale": False, "lastSynced": last_synced_at(settings.url)})

    @app.post("/api/projects/<project>/publish")
    def shared_publish_start(project: str) -> tuple[Response, int]:
        try:
            validate_path_segment(project)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        settings = read_settings()
        if not settings.url:
            return jsonify({"error": "no shared repository configured"}), 400
        outcome = start_publish(
            project, settings.url, evaluations_root=Path(reports_dir())
        )
        if outcome == "already_running":
            return jsonify({"error": "a publish is already running"}), 409
        if outcome != "started":
            return (
                jsonify({"error": "could not start the publish job, see server logs"}),
                500,
            )
        return jsonify({"started": True}), 202

    # -- pull a shared project into local evaluations -----------------------
    #
    # This is a deliberate, spec-approved exception to the read-only
    # invariant documented at the top of this module: it mutates LOCAL
    # state (the local reports directory, via import_zip_stream), not the
    # shared repository clone itself. The clone is only read from to build
    # the in-memory zip. It is therefore intentionally included in the
    # allowed-mutations set of the read-only sweep test
    # (tests/api/test_routes_shared_read.py::test_no_mutating_routes_under_shared).
    @app.post("/api/shared/projects/<project>/pull")
    @_with_shared_root
    def shared_pull(project: str, eval_root: Path, url: str) -> Response | tuple[Response, int]:
        """Materialize a shared project as a local copy.

        Body: optional JSON ``{"action": "copy"|"replace"}`` to resolve a 409
        collision returned from a previous attempt -- same semantics as the
        manual ``POST /api/projects/import`` route, since both funnel through
        ``import_zip_stream``.
        """
        err = _validate_segment(project)
        if err:
            return err
        project_path = _shared_project_dir(eval_root, project)
        if project_path is None:
            body, status = error_response("Invalid parameter", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        if not project_path.is_dir():
            body, status = error_response(
                "Project not found in the shared repository", HTTPStatus.NOT_FOUND, "NOT_FOUND",
            )
            return jsonify(body), status

        payload = request.get_json(silent=True) or {}
        action = payload.get("action")
        if action is not None and not isinstance(action, str):
            body, status = error_response("action must be a string", HTTPStatus.BAD_REQUEST, "INVALID_ACTION")
            return jsonify(body), status

        try:
            zip_path = _build_project_zip(project_path)
        except ValueError:
            body, status = error_response(
                "Project too large to pull", HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "TOO_LARGE",
            )
            return jsonify(body), status
        except (OSError, zipfile.BadZipFile):
            _logger.exception("Failed to build zip for shared pull of %s", project)
            body, status = error_response(
                "Failed to build project archive from the shared repository",
                HTTPStatus.INTERNAL_SERVER_ERROR, "EXPORT_ERROR",
            )
            return jsonify(body), status

        try:
            with zip_path.open("rb") as stream:
                return import_zip_stream(stream, reports_dir(), action)
        except OSError:
            _logger.exception("Failed to read zip for shared pull of %s", project)
            body, status = error_response(
                "Failed to read project archive from the shared repository",
                HTTPStatus.INTERNAL_SERVER_ERROR, "EXPORT_ERROR",
            )
            return jsonify(body), status
        finally:
            try:
                zip_path.unlink()
            except OSError as exc:
                _logger.warning("Failed to remove temp zip %s: %s", zip_path, exc)

    # -- read-only mirrors of the project read endpoints -------------------
    #
    # Each route below delegates to the SAME service function its local
    # counterpart uses (see api/routes_project_list.py, routes_project_data.py,
    # _scores_routes.py, routes_runs.py, routes_findings.py), with the shared
    # clone's evaluations root standing in for the local reports directory.
    # The response shape is therefore identical to the local route's; only the
    # data source differs.

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
            ok, _ = refresh_shared_clone(url)
            if ok:
                sync_shared_index(url)
                stale = False
            else:
                stale = True
        # backfill=False: the shared clone is a git worktree, not a local
        # evaluations dir -- writing onboardingCompletedAt into
        # repository_info.json here would dirty it, and a dirty worktree can
        # make publish's `pull --rebase` refuse (confusing wedge) the next
        # time someone publishes into this clone.
        projects = _fs_projects.build_project_list(eval_root, backfill=False)
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
            body, status = error_response("Invalid parameter", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
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
            body, status = error_response("Invalid parameter", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        return jsonify(verified_entries(project_dir))
