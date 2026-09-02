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
import os
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response, scan_target_error as _scan_target_error
from quodeq.services._fs_project_helpers import (
    project_record_exists,
    read_project_record,
)
from quodeq.services._fs_scan import scan_project
from quodeq.shared.validation import validate_path_segment


def _reports_dir() -> str:
    from quodeq.api import routes_project_list as _facade
    return _facade.reports_dir()


def project_scan(project: str) -> Response | tuple[Response, int]:
    """Return scan data for a project. Triggers scan if needed for local projects."""
    try:
        validate_path_segment(project)
    except ValueError:
        body, status = error_response("Invalid project name", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
        return jsonify(body), status

    # Same containment shape as project_estimates below — the normpath +
    # startswith form is the one CodeQL/Snyk recognize as a barrier.
    root = os.path.realpath(_reports_dir())
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
    root = os.path.realpath(_reports_dir())
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


def scan_path() -> Response | tuple[Response, int]:
    """Scan a local directory path directly (no registered project required)."""
    data = request.get_json(silent=True) or {}
    target = data.get("path", "").strip()
    if not target:
        body, status = error_response("path is required", HTTPStatus.BAD_REQUEST, "MISSING_PATH")
        return jsonify(body), status

    target_path = Path(target).resolve()
    # Allowlist: only permit paths under user home or the evaluations directory
    err = _scan_target_error(target_path, _reports_dir())
    if err is not None:
        body, status = err
        return jsonify(body), status
    if not target_path.is_dir():
        body, status = error_response("Path is not a directory", HTTPStatus.BAD_REQUEST, "NOT_DIR")
        return jsonify(body), status

    result = scan_project(target_path)
    return jsonify(dataclasses.asdict(result))


def register_project_scan_routes(app: Flask) -> None:
    """Register scan and estimate routes for projects."""
    app.get("/api/projects/<project>/scan")(project_scan)
    app.get("/api/projects/<project>/estimates")(project_estimates)
    app.post("/api/scan")(scan_path)
