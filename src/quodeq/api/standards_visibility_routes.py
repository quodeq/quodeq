"""GET/PUT the per-project visible-standards selection.

The file lives inside the analyzed repository
(``<repo>/.quodeq/standards-visibility.json``) so the dashboard and the
assistant both read one selection (there is no CLI consumer). See
core.standards.visibility.
"""
from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api._assistant_helpers import resolve_repo_root
from quodeq.api._constants import ERROR_CODE_BAD_REQUEST
from quodeq.api.helpers import error_response, project_root_or_error
from quodeq.core.standards.visibility import DEFAULT_VISIBLE_STANDARDS, validate_visible_ids
from quodeq.services.standards_prefs import (
    load_visible_standard_ids,
    save_visible_standard_ids,
    visibility_is_default,
)
from quodeq.services.standards import StandardsService

logger = logging.getLogger(__name__)


def _project_root_or_error(project_id: str) -> tuple[Path | None, Response | None]:
    """Validate *project_id* and resolve its local repository root.

    Returns ``(root, None)`` or ``(None, error_response)``.
    """
    return project_root_or_error(project_id, resolve_repo_root)


def _known_ids(app: Flask) -> set[str]:
    service = StandardsService(
        Path(app.config["STANDARDS_EVALUATORS_DIR"]),
        Path(app.config["STANDARDS_COMPILED_DIR"]),
        Path(app.config["STANDARDS_DIMENSIONS_FILE"]),
    )
    return {m.id.strip().lower() for m in service.list_standards()}


def _payload(app: Flask, root: Path, *, known_ids: set[str] | None = None) -> dict:
    ids = load_visible_standard_ids(root)
    return {
        "visibleStandardIds": list(ids),
        "isDefault": visibility_is_default(root),
        "knownStandardIds": sorted(known_ids if known_ids is not None else _known_ids(app)),
        # Additive: lets the UI's boot-time JS literal (constants.js)
        # be reconciled against the server's own default set instead
        # of duplicating it as a second source of truth.
        "defaultStandardIds": list(DEFAULT_VISIBLE_STANDARDS),
    }


def register_visibility_routes(app: Flask) -> None:
    """Register GET/PUT endpoints for the per-project standards selection."""

    @app.get("/api/projects/<project_id>/standards-visibility")
    def get_standards_visibility(project_id: str) -> Response:
        root, err = _project_root_or_error(project_id)
        if err is not None:
            return err
        return jsonify(_payload(app, root))

    @app.put("/api/projects/<project_id>/standards-visibility")
    def put_standards_visibility(project_id: str) -> Response:
        root, err = _project_root_or_error(project_id)
        if err is not None:
            return err
        body = request.get_json(force=True, silent=True)
        raw = body.get("visibleStandardIds") if isinstance(body, dict) else None
        if raw is None:
            return error_response('Body must be {"visibleStandardIds": [...]}',
                                  HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST)
        known = _known_ids(app)
        clean, errors = validate_visible_ids(raw, known)
        if errors:
            resp = jsonify({"error": "Invalid visibility selection",
                            "code": "invalid_visibility", "details": errors})
            resp.status_code = HTTPStatus.BAD_REQUEST
            return resp
        save_visible_standard_ids(root, clean)
        logger.info("standards.visibility saved project=%s visible=%d",
                    project_id, len(clean))
        return jsonify(_payload(app, root, known_ids=known))
