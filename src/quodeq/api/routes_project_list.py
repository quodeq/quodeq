"""Project listing, mutation, and export routes."""
from __future__ import annotations

import dataclasses
import json
import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.api.import_project import import_project as _import_project
from quodeq.api.routes_common import reports_dir
from quodeq.api.zip import export_project_zip
from quodeq.services._fs_clone import CloneError
from quodeq.services._fs_scan import scan_project
from quodeq.services.base import ActionProvider
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)
_BLOCKED_SCAN_PATHS = ("/proc", "/sys", "/dev", "/etc", "/var/run", "/private/etc", "/private/var/run")


def _scan_target_error(target_path: Path, reports_root: str) -> tuple[dict, int] | None:
    """Validate a resolved directory path against the scan allowlist.

    Shared by /api/scan and create_project's local-repo branch so both enforce
    the same rules: the path must live under the user's home or the
    evaluations directory, and must not be a blocked system path. Returns an
    ``error_response`` tuple on rejection, or None when the path is allowed.
    """
    _home = Path.home().resolve()
    _eval_dir = Path(reports_root).resolve()
    _allowed_roots = (_home, _eval_dir)
    if not any(target_path == root or target_path.is_relative_to(root) for root in _allowed_roots):
        return error_response(
            "Scan path must be under home directory", HTTPStatus.FORBIDDEN, "FORBIDDEN",
        )
    # Block scanning system directories to prevent information disclosure
    if any(str(target_path).startswith(b) for b in _BLOCKED_SCAN_PATHS):
        return error_response("Cannot scan system directories", HTTPStatus.FORBIDDEN, "FORBIDDEN")
    return None


def _find_existing_project(reports_root: str, repo: str, scope_path: str | None) -> str | None:
    """Return an existing project UUID matching the given repo identity, or None.

    Walks the reports directory looking for a project whose
    ``repository_info.json`` matches the resolved repo path/url, project name
    and (optional) scope_path. Pure read-only check — never mutates state.
    """
    from quodeq.shared.utils import is_repo_url, project_name_from_repo

    try:
        is_url = is_repo_url(repo)
    except ValueError:
        return None
    repo_resolved = repo if is_url else str(Path(repo).resolve())
    expected_name = project_name_from_repo(repo)
    reports_path = Path(reports_root)
    if not reports_path.is_dir():
        return None
    for child in reports_path.iterdir():
        if not child.is_dir():
            continue
        info_file = child / "repository_info.json"
        if not info_file.exists():
            continue
        try:
            data = json.loads(info_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("name") != expected_name:
            continue
        if data.get("path") != repo_resolved:
            continue
        if (data.get("scopePath") or None) != (scope_path or None):
            continue
        return child.name
    return None


def _rollback_new_dirs(reports_root: str, before: set[str]) -> None:
    """Delete any project directories created since *before* was captured."""
    import shutil

    reports_path = Path(reports_root)
    if not reports_path.is_dir():
        return
    after = {p.name for p in reports_path.iterdir() if p.is_dir()}
    for new in after - before:
        try:
            shutil.rmtree(reports_path / new, ignore_errors=True)
        except OSError:
            pass


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
        offset = request.args.get("offset", 0, type=int)
        limit = request.args.get("limit", 0, type=int)
        if offset > 0:
            projects = projects[offset:]
        if limit > 0:
            projects = projects[:limit]
        return jsonify({**result, "projects": projects})

    @app.patch("/api/projects/<project>/path")
    def update_project_path(project: str) -> Response | tuple[Response, int]:
        """Update the local filesystem path for a project."""
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
        return _handle_delete_project(provider)

    @app.get("/api/projects/<project>/info")
    def project_info(project: str) -> Response | tuple[Response, int]:
        """Return repository metadata for a project."""
        info = provider.get_project_info(reports_dir(), project)
        if not info:
            body, status = error_response("Project info not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(info)

    @app.get("/api/projects/<project>/scan")
    def project_scan(project: str) -> Response | tuple[Response, int]:
        """Return scan data for a project. Triggers scan if needed for local projects."""
        validate_path_segment(project)

        project_dir = Path(reports_dir()) / project
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

        # Check if local — read repository_info.json
        info_path = project_dir / "repository_info.json"
        if not info_path.exists():
            body, status = error_response("No scan available", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status

        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
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

    @app.post("/api/projects")
    def create_project() -> Response | tuple[Response, int]:
        """Register a new project (clone + scan) without starting an evaluation.

        Body: ``{ repo, cloneDest?, ephemeral?, branch?, scopePath?, discipline? }``

        For URL repos: requires either ``cloneDest`` (existing dir under home)
        or ``ephemeral: true``. For local-path repos: ``cloneDest`` and
        ``ephemeral`` are ignored.
        """
        from quodeq.services.evaluation_mixin import _register_project
        from quodeq.shared.utils import is_repo_url

        data = request.get_json(silent=True) or {}
        repo = (data.get("repo") or "").strip()
        if not repo:
            body, status = error_response("repo is required", HTTPStatus.BAD_REQUEST, "MISSING_REPO")
            return jsonify(body), status

        scope_path = data.get("scopePath") or None
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
                dest_path = Path(clone_dest)
                home = Path.home().resolve()
                try:
                    dest_resolved = dest_path.resolve()
                except OSError:
                    body, status = error_response(
                        "Invalid cloneDest path",
                        HTTPStatus.BAD_REQUEST,
                        "INVALID_CLONE_DEST",
                    )
                    return jsonify(body), status
                if not dest_resolved.is_dir() or not dest_resolved.is_relative_to(home):
                    body, status = error_response(
                        "cloneDest must be an existing directory under your home folder",
                        HTTPStatus.BAD_REQUEST,
                        "INVALID_CLONE_DEST",
                    )
                    return jsonify(body), status
        else:
            # For local repos, fail fast if the path doesn't exist — registering
            # a project for a missing directory would leave an orphan UUID dir
            # behind that the caller has no way to recover from.
            local_candidate = Path(repo)
            if not local_candidate.exists() or not local_candidate.is_dir():
                body, status = error_response(
                    "Local repo path does not exist or is not a directory",
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

        # Pre-flight: detect duplicates by walking existing project
        # directories. Returns None if no match.
        existing = _find_existing_project(reports_root, repo, scope_path)
        if existing is not None:
            return (
                jsonify({"error": "Project already exists", "existingProjectId": existing}),
                HTTPStatus.CONFLICT,
            )

        # Capture the set of project directories present before registration
        # so we can roll back any directory created during a failed scan.
        reports_root_path = Path(reports_root)
        before = (
            {p.name for p in reports_root_path.iterdir() if p.is_dir()}
            if reports_root_path.is_dir()
            else set()
        )

        try:
            project_uuid = _register_project(
                repo,
                discipline,
                reports_root,
                scope_path=scope_path,
                clone_dest=clone_dest,
                ephemeral=ephemeral,
            )
        except (FileNotFoundError, ValueError) as exc:
            _rollback_new_dirs(reports_root, before)
            body, status = error_response(str(exc), HTTPStatus.BAD_REQUEST, "INVALID_REPO")
            return jsonify(body), status
        except CloneError as exc:
            _rollback_new_dirs(reports_root, before)
            code_map = {
                "auth": ("AUTH_REQUIRED", HTTPStatus.BAD_REQUEST),
                "network": ("NETWORK_ERROR", HTTPStatus.BAD_GATEWAY),
                "repo_not_found": ("REPO_NOT_FOUND", HTTPStatus.NOT_FOUND),
                "dest_exists": ("DEST_EXISTS", HTTPStatus.CONFLICT),
                "disk": ("DISK_ERROR", HTTPStatus.INSUFFICIENT_STORAGE),
                "unknown": ("CLONE_FAILED", HTTPStatus.BAD_GATEWAY),
            }
            code, status = code_map.get(exc.kind, ("CLONE_FAILED", HTTPStatus.BAD_GATEWAY))
            body, _ = error_response(str(exc), status, code)
            return jsonify(body), status
        except Exception as exc:  # pragma: no cover — unexpected scan/clone failure
            # error_response swallows the traceback that Flask's own 500
            # handler would have logged; record it before converting.
            _logger.exception("Registration failed for repo=%r", repo)
            _rollback_new_dirs(reports_root, before)
            # Return a generic message; the exception detail (which can carry
            # filesystem paths or backend internals) is logged above, not sent
            # to the remote caller.
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

        # scan.json is now always present after _register_project succeeds.
        scan_path = Path(reports_root) / project_uuid / "scan.json"
        try:
            scan_data = json.loads(scan_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, FileNotFoundError):
            scan_data = {
                "total_files": 0,
                "code_files": 0,
                "languages": {},
                "branches": [],
                "modules": [],
                "file_tree": [],
            }

        return jsonify({"projectId": project_uuid, "scanData": scan_data})

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
