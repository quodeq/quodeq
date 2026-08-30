"""GET/PUT per-project standards threshold overrides.

The override file lives inside the analyzed repository
(``<repo>/.quodeq/standards-overrides.json``) so the whole team shares it.
"""
from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api._assistant_helpers import resolve_repo_root
from quodeq.api.helpers import error_response
from quodeq.shared.validation import validate_path_segment
from quodeq.core.standards.overrides import validate_overrides
from quodeq.services.standards_overrides import changed_dimensions, override_counts_by_dimension
from quodeq.services.standards_prefs import (
    clear_project_overrides,
    collect_declared_params,
    load_project_overrides,
    save_project_overrides,
)

logger = logging.getLogger(__name__)


def register_overrides_routes(app: Flask) -> None:
    """Register GET/PUT endpoints for per-project standards threshold overrides."""

    def _repo_root(project_id: str) -> Path | None:
        root = resolve_repo_root(project_id)
        return Path(root) if root else None

    @app.get("/api/projects/<project_id>/standards-overrides")
    def get_standards_overrides(project_id: str) -> Response:
        try:
            validate_path_segment(project_id)
        except ValueError:
            return error_response("Invalid project id", HTTPStatus.BAD_REQUEST, "bad_request")
        root = _repo_root(project_id)
        if root is None:
            return error_response("Project has no local repository", HTTPStatus.NOT_FOUND, "not_found")
        compiled_dir = Path(app.config["STANDARDS_COMPILED_DIR"])
        overrides = load_project_overrides(root)
        return jsonify({"overrides": overrides, "counts": override_counts_by_dimension(overrides, compiled_dir)})

    @app.put("/api/projects/<project_id>/standards-overrides")
    def put_standards_overrides(project_id: str) -> Response:
        try:
            validate_path_segment(project_id)
        except ValueError:
            return error_response("Invalid project id", HTTPStatus.BAD_REQUEST, "bad_request")
        root = _repo_root(project_id)
        if root is None:
            return error_response("Project has no local repository", HTTPStatus.NOT_FOUND, "not_found")
        payload = request.get_json(force=True)
        raw = payload.get("overrides") if isinstance(payload, dict) else None
        if raw is None:
            return error_response(
                'Body must be {"overrides": {...}}', HTTPStatus.BAD_REQUEST, "bad_request"
            )
        compiled_dir = Path(app.config["STANDARDS_COMPILED_DIR"])
        evaluators_dir = Path(app.config["STANDARDS_EVALUATORS_DIR"])
        # Merge compiled (managed) params with custom-standards params.
        # Duplicated custom standards keep the original requirement IDs, so both
        # dirs may declare the same req-id with identical specs — merging is safe;
        # compiled declarations win on collision (dict-update order: evaluators first).
        declared = {**collect_declared_params(evaluators_dir), **collect_declared_params(compiled_dir)}
        clean, errors = validate_overrides(raw, declared)
        if errors:
            resp = jsonify({"error": "Invalid overrides", "code": "invalid_overrides", "details": errors})
            resp.status_code = HTTPStatus.BAD_REQUEST
            return resp
        current = load_project_overrides(root)
        changed = changed_dimensions(compiled_dir, current, clean)
        dry_run = request.args.get("dryRun", "").lower() in ("1", "true")
        if dry_run:
            return jsonify({"overrides": clean, "changedDimensions": changed})
        if not clean:
            clear_project_overrides(root)
            logger.info("standards.overrides cleared project=%s", project_id)
            return jsonify({"overrides": {}, "changedDimensions": changed})
        save_project_overrides(root, clean)
        logger.info("standards.overrides saved project=%s reqs=%d", project_id, len(clean))
        return jsonify({"overrides": clean, "changedDimensions": changed})
