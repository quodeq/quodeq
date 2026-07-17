"""GET/PUT per-project standards threshold overrides.

The override file lives inside the analyzed repository
(``<repo>/.quodeq/standards-overrides.json``) so the whole team shares it.
"""
from __future__ import annotations

import json
import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api._assistant_helpers import resolve_repo_root
from quodeq.api.helpers import error_response
from quodeq.core.standards.overrides import (
    OVERRIDES_RELPATH,
    collect_declared_params,
    dimension_params,
    load_project_overrides,
    validate_overrides,
)

logger = logging.getLogger(__name__)


def _counts(overrides: dict, compiled_dir: Path) -> dict[str, int]:
    """Per-dimension count of overridden requirements, keyed by compiled id."""
    dim_by_req: dict[str, str] = {}
    for path in sorted(compiled_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        for principle in data.get("principles", []):
            for req in principle.get("requirements", []):
                if req.get("id"):
                    dim_by_req[req["id"]] = data.get("id", path.stem)
    counts: dict[str, int] = {}
    for req_id in overrides:
        dim = dim_by_req.get(req_id)
        if dim:
            counts[dim] = counts.get(dim, 0) + 1
    return counts


def _changed_dimensions(compiled_dir: Path, current: dict, proposed: dict) -> list[str]:
    """Dimensions whose non-default effective params differ between the
    current overrides file and the proposed mapping. A changed dimension is
    exactly one whose cache keys will shift, so this is the invalidation
    impact surfaced to the user before saving.

    Scans only the compiled dir, mirroring dimension_params_state (which reads
    only compiled/<dimension>.json), so custom evaluator-dir standards—whose
    cache keys never shift on override change—are symmetrically never reported."""
    changed: list[str] = []
    for path in sorted(compiled_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        _, before = dimension_params(data, current)
        _, after = dimension_params(data, proposed)
        if before != after:
            changed.append(data.get("id", path.stem))
    return changed


def register_overrides_routes(app: Flask) -> None:
    """Register GET/PUT endpoints for per-project standards threshold overrides."""

    def _repo_root(project_id: str) -> Path | None:
        root = resolve_repo_root(project_id)
        return Path(root) if root else None

    @app.get("/api/projects/<project_id>/standards-overrides")
    def get_standards_overrides(project_id: str) -> Response:
        root = _repo_root(project_id)
        if root is None:
            return error_response("Project has no local repository", HTTPStatus.NOT_FOUND, "not_found")
        compiled_dir = Path(app.config["STANDARDS_COMPILED_DIR"])
        overrides = load_project_overrides(root)
        return jsonify({"overrides": overrides, "counts": _counts(overrides, compiled_dir)})

    @app.put("/api/projects/<project_id>/standards-overrides")
    def put_standards_overrides(project_id: str) -> Response:
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
        changed = _changed_dimensions(compiled_dir, current, clean)
        dry_run = request.args.get("dryRun", "").lower() in ("1", "true")
        if dry_run:
            return jsonify({"overrides": clean, "changedDimensions": changed})
        override_path = root / OVERRIDES_RELPATH
        if not clean:
            override_path.unlink(missing_ok=True)
            logger.info("standards.overrides cleared project=%s", project_id)
            return jsonify({"overrides": {}, "changedDimensions": changed})
        override_path.parent.mkdir(parents=True, exist_ok=True)
        override_path.write_text(json.dumps({"version": 1, "overrides": clean}, indent=2) + "\n", encoding="utf-8")
        logger.info("standards.overrides saved project=%s reqs=%d", project_id, len(clean))
        return jsonify({"overrides": clean, "changedDimensions": changed})
