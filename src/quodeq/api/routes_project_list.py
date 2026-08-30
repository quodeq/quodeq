"""Project listing, mutation, and export routes."""
from __future__ import annotations

import dataclasses
import json
import logging
import os
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response, scan_target_error as _scan_target_error
from quodeq.core.types import to_camel_dict
from quodeq.api.import_project import import_project as _import_project
from quodeq.api.routes_common import reports_dir
from quodeq.api.zip import export_project_zip
from quodeq.services._fs_project_helpers import (
    project_record_exists,
    read_project_record,
)
from quodeq.services._fs_scan import scan_project
from quodeq.services._warmup import engine as warmup_engine
from quodeq.services.base import ActionProvider, NewProjectSpec
from quodeq.shared.validation import contained_path, validate_path_segment, validate_relative_scope

_logger = logging.getLogger(__name__)


def _handle_delete_project(provider: ActionProvider) -> Response | tuple[Response, int]:
    """Handle DELETE /api/projects/<project>."""
    project = request.view_args["project"]
    if request.args.get("confirm") != "true":
        body, status = error_response("Use ?confirm=true to confirm deletion", HTTPStatus.BAD_REQUEST, "CONFIRMATION_REQUIRED")
        return jsonify(body), status
    _logger.info("delete_project: project=%s, remote_addr=%s", project, request.remote_addr)
    ok = provider.delete_project(reports_dir(), project)
    if not ok:
        body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        return jsonify(body), status
    return jsonify({"deleted": project})


def _handle_update_project_path(provider: ActionProvider) -> Response | tuple[Response, int]:
    """Handle PATCH /api/projects/<project>/path."""
    project = request.view_args["project"]
    data = request.get_json(silent=True) or {}
    new_path = data.get("path", "").strip()
    if not new_path:
        body, status = error_response("Path is required", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
        return jsonify(body), status
    try:
        # Reject literal '..' segments in user input — even if they resolve
        # to a fine canonical path, accepting them silently transforms what
        # the user typed into something different. Then resolve and verify
        # the canonical form is still absolute and traversal-free.
        if ".." in Path(new_path).parts:
            raise ValueError("path contains parent-directory segment")
        candidate = Path(new_path)
        if not candidate.is_absolute():
            raise ValueError("path must be absolute")
        resolved = candidate.resolve(strict=False)
        if not resolved.is_absolute() or ".." in resolved.parts:
            raise ValueError("path resolves to a non-canonical location")
    except (OSError, ValueError):
        body, status = error_response("Invalid path", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
        return jsonify(body), status
    new_path = str(resolved)
    _logger.info("update_project_path: project=%s, remote_addr=%s", project, request.remote_addr)
    ok = provider.update_project_path(reports_dir(), project, new_path)
    if not ok:
        body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        return jsonify(body), status
    return jsonify({"updated": project, "path": new_path})


def register_project_list_routes(app: Flask, provider: ActionProvider) -> None:
    """Register project listing, mutation, and export routes."""

    @app.get("/api/projects")
    def list_projects() -> Response:
        """Return all projects with optional ``?limit=N&offset=M`` pagination."""
        result = provider.list_projects(reports_dir())
        projects = result.get("projects", [])
        # Self-healing warm-up: anything still pending goes (back) on the
        # queue before pagination, so unpolled pages heal too.
        for entry in projects:
            if getattr(entry, "summary_pending", False):
                warmup_engine.enqueue(entry.id)
        offset = request.args.get("offset", 0, type=int)
        limit = request.args.get("limit", 0, type=int)
        if offset > 0:
            projects = projects[offset:]
        if limit > 0:
            projects = projects[:limit]
        # Serialize at the boundary: providers hand back ProjectEntry
        # entities (or already-serialized dicts from remote providers).
        wire = [p if isinstance(p, dict) else to_camel_dict(p) for p in projects]
        payload = {**result, "projects": wire}
        snapshot = warmup_engine.snapshot()
        if snapshot is not None:
            payload["warmup"] = snapshot
        return jsonify(payload)

    @app.patch("/api/projects/<project>/path")
    def update_project_path(project: str) -> Response | tuple[Response, int]:
        """Update the local filesystem path for a project."""
        try:
            validate_path_segment(project)
        except ValueError:
            body, status = error_response("Invalid project name", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        return _handle_update_project_path(provider)

    @app.get("/api/projects/<project>/export")
    def export_project(project: str) -> Response | tuple[Response, int]:
        """Export a project as a ZIP archive."""
        return export_project_zip(project, reports_dir())

    @app.post("/api/projects/import")
    def import_project_route() -> Response | tuple[Response, int]:
        """Import a previously-exported project ZIP archive.

        Body: ``multipart/form-data`` with a ``file`` field containing the zip
        and an optional ``action`` field (``replace`` or ``copy``) used to
        resolve a 409 collision returned from a prior call.
        """
        return _import_project(reports_dir())

    @app.delete("/api/projects/<project>")
    def delete_project(project: str) -> Response | tuple[Response, int]:
        """Delete a project and all its run data."""
        try:
            validate_path_segment(project)
        except ValueError:
            body, status = error_response("Invalid project name", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        return _handle_delete_project(provider)

    @app.get("/api/projects/<project>/info")
    def project_info(project: str) -> Response | tuple[Response, int]:
        """Return repository metadata for a project."""
        try:
            validate_path_segment(project)
        except ValueError:
            body, status = error_response("Invalid project name", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        info = provider.get_project_info(reports_dir(), project)
        if not info:
            body, status = error_response("Project info not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(info)

    @app.get("/api/projects/<project>/scan")
    def project_scan(project: str) -> Response | tuple[Response, int]:
        """Return scan data for a project. Triggers scan if needed for local projects."""
        try:
            validate_path_segment(project)
        except ValueError:
            body, status = error_response("Invalid project name", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status

        # Same containment shape as project_estimates below — the normpath +
        # startswith form is the one CodeQL/Snyk recognize as a barrier.
        root = os.path.realpath(reports_dir())
        candidate = os.path.normpath(os.path.join(root, project))
        if not candidate.startswith(root + os.sep):
            body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        project_dir = Path(candidate)
        if not project_dir.is_dir():
            body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status

        scan_path = project_dir / "scan.json"
        if scan_path.exists():
            try:
                data = json.loads(scan_path.read_text(encoding="utf-8"))
                return jsonify(data)
            except (json.JSONDecodeError, OSError):
                pass

        # Check if local — read the project's repository record (via the
        # service layer; the route keeps no repository_info.json knowledge).
        if not project_record_exists(project_dir):
            body, status = error_response("No scan available", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status

        info = read_project_record(project_dir)
        if info is None:
            body, status = error_response("Could not read project info", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL")
            return jsonify(body), status

        if info.get("location") != "local" or not info.get("path"):
            body, status = error_response("Scan only available for local projects", HTTPStatus.BAD_REQUEST, "NOT_LOCAL")
            return jsonify(body), status

        project_path = Path(info["path"])
        if not project_path.is_dir():
            body, status = error_response("Project path not found on disk", HTTPStatus.NOT_FOUND, "PATH_MISSING")
            return jsonify(body), status

        result = scan_project(project_path, output_dir=project_dir)
        return jsonify(dataclasses.asdict(result))

    @app.get("/api/projects/<project>/estimates")
    def project_estimates(project: str) -> Response | tuple[Response, int]:
        """Return read-only pre-run per-dimension file estimates for a project.

        Query params: ``dimensions`` = comma-separated dimension ids (omitted
        or empty → all dimensions available for the project; unknown ids are
        ignored), ``cleanScan`` = "true"/"false" (default false). With
        cleanScan=true each dimension reports count=total and cached=0.
        Never creates a run or writes to disk.
        """
        try:
            validate_path_segment(project)
        except ValueError:
            body, status = error_response("Invalid project name", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status

        # Containment check in the exact normpath + startswith shape CodeQL
        # recognizes as a path-injection barrier (pathlib's is_relative_to
        # is not modeled and left the alerts open).
        root = os.path.realpath(reports_dir())
        candidate = os.path.normpath(os.path.join(root, project))
        if not candidate.startswith(root + os.sep):
            body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        project_dir = Path(candidate)
        if not project_dir.is_dir():
            body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status

        # Lazy import: pulls in the analysis pipeline, which the API process
        # should not pay for at startup. Layer exception is baselined — same
        # seam as api/_evaluation_routes.py.
        from quodeq.analysis.estimates import project_estimates_payload

        raw_dims = request.args.get("dimensions", "")
        requested = [d.strip() for d in raw_dims.split(",") if d.strip()] or None
        clean_scan = request.args.get("cleanScan", "false").strip().lower() == "true"
        return jsonify(project_estimates_payload(project_dir, requested, clean_scan))

    @app.post("/api/projects")
    def create_project() -> Response | tuple[Response, int]:
        """Register a new project (clone + scan) without starting an evaluation.

        Body: ``{ repo, cloneDest?, ephemeral?, branch?, scopePath?, discipline? }``

        For URL repos: requires either ``cloneDest`` (existing dir under home)
        or ``ephemeral: true``. For local-path repos: ``cloneDest`` and
        ``ephemeral`` are ignored.
        """
        from quodeq.shared.utils import is_repo_url

        data = request.get_json(silent=True) or {}
        repo = (data.get("repo") or "").strip()
        if not repo:
            body, status = error_response("repo is required", HTTPStatus.BAD_REQUEST, "MISSING_REPO")
            return jsonify(body), status

        scope_path = data.get("scopePath") or None
        if scope_path is not None:
            try:
                validate_relative_scope(str(scope_path))
            except ValueError as exc:
                body, status = error_response(str(exc), HTTPStatus.BAD_REQUEST, "INVALID_SCOPE")
                return jsonify(body), status
        discipline = data.get("discipline") or None
        clone_dest = data.get("cloneDest") or None
        ephemeral = bool(data.get("ephemeral", False))
        reports_root = reports_dir()

        try:
            is_url = is_repo_url(repo)
        except ValueError:
            body, status = error_response("Invalid repo URL", HTTPStatus.BAD_REQUEST, "INVALID_REPO_URL")
            return jsonify(body), status

        if is_url:
            if not ephemeral and not clone_dest:
                body, status = error_response(
                    "cloneDest is required for URL repos when ephemeral is false",
                    HTTPStatus.BAD_REQUEST,
                    "MISSING_CLONE_DEST",
                )
                return jsonify(body), status
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
                    return jsonify(body), status
                except ValueError:
                    body, status = error_response(
                        "cloneDest must be an existing directory under your home folder",
                        HTTPStatus.BAD_REQUEST,
                        "INVALID_CLONE_DEST",
                    )
                    return jsonify(body), status
                # Hand the *contained* path to the cloner. The previous code
                # resolved into a local and then passed the raw request string
                # on, so the check guarded a value nothing downstream used.
                clone_dest = dest
        else:
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

        spec = NewProjectSpec(
            repo=repo, discipline=discipline, scope_path=scope_path,
            clone_dest=clone_dest, ephemeral=ephemeral,
        )
        result = provider.create_project(reports_root, spec)

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

        # The 5s ProjectsCache would otherwise hide the new project from an
        # immediately-following GET /api/projects (the wizard refetches the
        # list as soon as it closes).
        provider.invalidate_projects_cache()
        return jsonify({"projectId": result.project_id, "scanData": result.scan_data})

    @app.post("/api/scan")
    def scan_path() -> Response | tuple[Response, int]:
        """Scan a local directory path directly (no registered project required)."""
        data = request.get_json(silent=True) or {}
        target = data.get("path", "").strip()
        if not target:
            body, status = error_response("path is required", HTTPStatus.BAD_REQUEST, "MISSING_PATH")
            return jsonify(body), status

        target_path = Path(target).resolve()
        # Allowlist: only permit paths under user home or the evaluations directory
        err = _scan_target_error(target_path, reports_dir())
        if err is not None:
            body, status = err
            return jsonify(body), status
        if not target_path.is_dir():
            body, status = error_response("Path is not a directory", HTTPStatus.BAD_REQUEST, "NOT_DIR")
            return jsonify(body), status

        result = scan_project(target_path)
        return jsonify(dataclasses.asdict(result))
