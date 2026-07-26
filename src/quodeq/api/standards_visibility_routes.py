"""GET/PUT the per-project visible-standards selection.

The file lives inside the analyzed repository
(``<repo>/.quodeq/standards-visibility.json``) so the dashboard, the CLI and
the assistant all read one selection. See core.standards.visibility.
"""
from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api._assistant_helpers import resolve_repo_root
from quodeq.api.helpers import error_response
from quodeq.core.standards.visibility import (
    VISIBILITY_RELPATH,
    load_visible_standard_ids,
    save_visible_standard_ids,
    validate_visible_ids,
)
from quodeq.services.standards import StandardsService

logger = logging.getLogger(__name__)


def register_visibility_routes(app: Flask) -> None:
    """Register GET/PUT endpoints for the per-project standards selection."""

    def _repo_root(project_id: str) -> Path | None:
        root = resolve_repo_root(project_id)
        return Path(root) if root else None

    def _known_ids() -> set[str]:
        service = StandardsService(
            Path(app.config["STANDARDS_EVALUATORS_DIR"]),
            Path(app.config["STANDARDS_COMPILED_DIR"]),
            Path(app.config["STANDARDS_DIMENSIONS_FILE"]),
        )
        return {m.id.strip().lower() for m in service.list_standards()}

    def _payload(root: Path) -> dict:
        ids = load_visible_standard_ids(root)
        return {
            "visibleStandardIds": list(ids),
            "isDefault": not (root / VISIBILITY_RELPATH).is_file(),
            "knownStandardIds": sorted(_known_ids()),
        }

    @app.get("/api/projects/<project_id>/standards-visibility")
    def get_standards_visibility(project_id: str) -> Response:
        root = _repo_root(project_id)
        if root is None:
            return error_response("Project has no local repository",
                                  HTTPStatus.NOT_FOUND, "not_found")
        return jsonify(_payload(root))

    @app.put("/api/projects/<project_id>/standards-visibility")
    def put_standards_visibility(project_id: str) -> Response:
        root = _repo_root(project_id)
        if root is None:
            return error_response("Project has no local repository",
                                  HTTPStatus.NOT_FOUND, "not_found")
        body = request.get_json(force=True, silent=True)
        raw = body.get("visibleStandardIds") if isinstance(body, dict) else None
        if raw is None:
            return error_response('Body must be {"visibleStandardIds": [...]}',
                                  HTTPStatus.BAD_REQUEST, "bad_request")
        clean, errors = validate_visible_ids(raw, _known_ids())
        if errors:
            resp = jsonify({"error": "Invalid visibility selection",
                            "code": "invalid_visibility", "details": errors})
            resp.status_code = HTTPStatus.BAD_REQUEST
            return resp
        save_visible_standard_ids(root, clean)
        logger.info("standards.visibility saved project=%s visible=%d",
                    project_id, len(clean))
        return jsonify(_payload(root))
