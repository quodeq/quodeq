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
from quodeq.api._constants import ERROR_CODE_BAD_REQUEST
from quodeq.api.helpers import error_response, project_root_or_error
from quodeq.core.standards.overrides import validate_overrides
from quodeq.services.standards_overrides import changed_dimensions, override_counts_by_dimension
from quodeq.services.standards_prefs import (
    clear_project_overrides,
    collect_declared_params,
    load_project_overrides,
    save_project_overrides,
)

logger = logging.getLogger(__name__)


def _project_root_or_error(project_id: str) -> tuple[Path | None, Response | None]:
    """Validate *project_id* and resolve its local repository root.

    Returns ``(root, None)`` or ``(None, error_response)``.
    """
    return project_root_or_error(project_id, resolve_repo_root)


def _declared_params(app: Flask) -> dict:
    """Every overridable parameter declared by compiled and custom standards.

    Duplicated custom standards keep the original requirement IDs, so both
    dirs may declare the same req-id with identical specs — merging is safe;
    compiled declarations win on collision (dict-update order: evaluators first).
    """
    compiled_dir = Path(app.config["STANDARDS_COMPILED_DIR"])
    evaluators_dir = Path(app.config["STANDARDS_EVALUATORS_DIR"])
    return {**collect_declared_params(evaluators_dir), **collect_declared_params(compiled_dir)}


def _invalid_overrides_response(errors: list) -> Response:
    resp = jsonify({"error": "Invalid overrides", "code": "invalid_overrides", "details": errors})
    resp.status_code = HTTPStatus.BAD_REQUEST
    return resp


def _persist_overrides(root: Path, project_id: str, clean: dict) -> None:
    """Save *clean* to the project, or clear the file when nothing is left."""
    if not clean:
        clear_project_overrides(root)
        logger.info("standards.overrides cleared project=%s", project_id)
        return
    save_project_overrides(root, clean)
    logger.info("standards.overrides saved project=%s reqs=%d", project_id, len(clean))


def _get_standards_overrides(app: Flask, project_id: str) -> Response:
    root, err = _project_root_or_error(project_id)
    if err is not None:
        return err
    compiled_dir = Path(app.config["STANDARDS_COMPILED_DIR"])
    overrides = load_project_overrides(root)
    return jsonify({"overrides": overrides, "counts": override_counts_by_dimension(overrides, compiled_dir)})


def _put_standards_overrides(app: Flask, project_id: str) -> Response:
    root, err = _project_root_or_error(project_id)
    if err is not None:
        return err
    payload = request.get_json(force=True)
    raw = payload.get("overrides") if isinstance(payload, dict) else None
    if raw is None:
        return error_response(
            'Body must be {"overrides": {...}}', HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST
        )
    clean, errors = validate_overrides(raw, _declared_params(app))
    if errors:
        return _invalid_overrides_response(errors)
    compiled_dir = Path(app.config["STANDARDS_COMPILED_DIR"])
    changed = changed_dimensions(compiled_dir, load_project_overrides(root), clean)
    dry_run = request.args.get("dryRun", "").lower() in ("1", "true")
    if not dry_run:
        _persist_overrides(root, project_id, clean)
    return jsonify({"overrides": clean, "changedDimensions": changed})


def register_overrides_routes(app: Flask) -> None:
    """Register GET/PUT endpoints for per-project standards threshold overrides."""

    @app.get("/api/projects/<project_id>/standards-overrides")
    def get_standards_overrides(project_id: str) -> Response:
        return _get_standards_overrides(app, project_id)

    @app.put("/api/projects/<project_id>/standards-overrides")
    def put_standards_overrides(project_id: str) -> Response:
        return _put_standards_overrides(app, project_id)
