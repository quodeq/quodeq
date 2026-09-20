"""Project scan and estimate routes.

Split from routes_project_list.py to keep that file under the size ratchet's
300-line cap. ``reports_dir`` is looked up dynamically through the
routes_project_list facade (rather than imported directly) so that
``patch("quodeq.api.routes_project_list.reports_dir", ...)`` in existing
tests still takes effect for these routes, which are registered from inside
``register_project_list_routes``.

Handlers are module-level functions attached to *app* via
``app.get(rule)(handler)`` in ``register_project_scan_routes`` rather than
via ``@app.get`` closures, so each handler is its own top-level function for
the size ratchet (a wrapping registrar over all three would itself exceed
the 50-line cap). Registration behavior is identical either way — the
decorator form and the direct-call form both end up calling
``app.add_url_rule`` with the same view function.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import _path_from_body, json_error, scan_target_error as _scan_target_error
from quodeq.services.fs_project_helpers import (
    project_record_exists,
    read_project_record,
)
from quodeq.services.fs_scan import scan_project
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)


def _reports_dir() -> str:
    from quodeq.api import routes_project_list as _facade
    return _facade.reports_dir()


def _contained_project_dir(project: str) -> Path | None:
    """Resolve *project* under the reports root, or None if it escapes or
    does not exist.

    Containment check in the exact normpath + startswith shape CodeQL
    recognizes as a path-injection barrier (pathlib's is_relative_to is
    not modeled and left the alerts open).
    """
    root = os.path.realpath(_reports_dir())
    candidate = os.path.normpath(os.path.join(root, project))
    if not candidate.startswith(root + os.sep):
        return None
    project_dir = Path(candidate)
    if not project_dir.is_dir():
        return None
    return project_dir


def _scan_inputs(project: str) -> tuple[Path | None, tuple[Response, int] | None]:
    """Resolve *project* to its directory under the reports root, or an error."""
    try:
        validate_path_segment(project)
    except ValueError:
        return None, json_error("Invalid project name", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
    project_dir = _contained_project_dir(project)
    if project_dir is None:
        return None, json_error("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
    return project_dir, None


def _cached_scan_response(project_dir: Path) -> Response | None:
    """The project's existing scan.json as a response, or None to rescan."""
    scan_path = project_dir / "scan.json"
    if not scan_path.exists():
        return None
    try:
        return jsonify(json.loads(scan_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError) as exc:
        _logger.debug("existing scan.json for %s unreadable, rescanning: %s", project_dir.name, exc)
        return None


def _local_scan_root(project_dir: Path) -> tuple[Path | None, tuple[Response, int] | None]:
    """The local source directory to scan for *project_dir*, or an error."""
    # Check if local — read the project's repository record (via the
    # service layer; the route keeps no repository_info.json knowledge).
    if not project_record_exists(project_dir):
        return None, json_error("No scan available", HTTPStatus.NOT_FOUND, "NOT_FOUND")
    info = read_project_record(project_dir)
    if info is None:
        return None, json_error(
            "Could not read project info", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL")
    if info.get("location") != "local" or not info.get("path"):
        return None, json_error(
            "Scan only available for local projects", HTTPStatus.BAD_REQUEST, "NOT_LOCAL")
    project_path = Path(info["path"])
    if not project_path.is_dir():
        return None, json_error(
            "Project path not found on disk", HTTPStatus.NOT_FOUND, "PATH_MISSING")
    return project_path, None


def _scan_response(result) -> Response:
    """Serialize a fresh scan result as the route's JSON response."""
    return jsonify(dataclasses.asdict(result))


def project_scan(project: str) -> Response | tuple[Response, int]:
    """Return scan data for a project. Triggers scan if needed for local projects."""
    project_dir, err = _scan_inputs(project)
    if err is not None:
        return err
    cached = _cached_scan_response(project_dir)
    if cached is not None:
        return cached
    project_path, err = _local_scan_root(project_dir)
    if err is not None:
        return err
    return _scan_response(scan_project(project_path, output_dir=project_dir))


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
        return json_error("Invalid project name", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")

    project_dir = _contained_project_dir(project)
    if project_dir is None:
        return json_error("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")

    # Lazy import: pulls in the analysis pipeline, which the API process
    # should not pay for at startup. Layer exception is baselined — same
    # seam as api/_evaluation_routes.py.
    from quodeq.analysis.estimates import project_estimates_payload

    raw_dims = request.args.get("dimensions", "")
    requested = [d.strip() for d in raw_dims.split(",") if d.strip()] or None
    clean_scan = request.args.get("cleanScan", "false").strip().lower() == "true"
    return jsonify(project_estimates_payload(project_dir, requested, clean_scan))


def scan_path() -> Response | tuple[Response, int]:
    """Scan a local directory path directly (no registered project required)."""
    data = request.get_json(silent=True) or {}
    target = _path_from_body(data)
    if isinstance(target, tuple):
        body, status = target
        return jsonify(body), status
    if not target:
        return json_error("path is required", HTTPStatus.BAD_REQUEST, "MISSING_PATH")

    target_path = Path(target).resolve()
    # Allowlist: only permit paths under user home or the evaluations directory
    err = _scan_target_error(target_path, _reports_dir())
    if err is not None:
        body, status = err
        return jsonify(body), status
    if not target_path.is_dir():
        return json_error("Path is not a directory", HTTPStatus.BAD_REQUEST, "NOT_DIR")

    result = scan_project(target_path)
    return jsonify(dataclasses.asdict(result))


def register_project_scan_routes(app: Flask) -> None:
    """Register scan and estimate routes for projects."""
    app.get("/api/projects/<project>/scan")(project_scan)
    app.get("/api/projects/<project>/estimates")(project_estimates)
    app.post("/api/scan")(scan_path)
