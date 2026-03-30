"""API routes for the Standards Browser & Editor."""
from __future__ import annotations
import logging
from pathlib import Path
from flask import Flask, Response, jsonify, request
from quodeq.api.helpers import error_response
from quodeq.core.types import to_camel_dict
from quodeq.services.standards import StandardsService

logger = logging.getLogger(__name__)

def _get_service(app: Flask) -> StandardsService:
    if not hasattr(app, "_standards_service"):
        app._standards_service = StandardsService(
            evaluators_dir=Path(app.config["STANDARDS_EVALUATORS_DIR"]),
            compiled_dir=Path(app.config["STANDARDS_COMPILED_DIR"]),
            dimensions_file=Path(app.config["STANDARDS_DIMENSIONS_FILE"]),
        )
    return app._standards_service

def _get_library_client(app: Flask):
    base_url = app.config.get("STANDARDS_LIBRARY_URL")
    if not base_url:
        return None
    from quodeq.services.standards_library import StandardsLibraryClient, UrllibJsonClient
    token = app.config.get("STANDARDS_LIBRARY_TOKEN")
    return StandardsLibraryClient(base_url=base_url, http_client=UrllibJsonClient(), token=token)

def _load_cwe_list(app: Flask) -> list[dict]:
    """Load and cache the CWE list."""
    if not hasattr(app, "_cwe_list"):
        cwe_path = Path(app.config["STANDARDS_COMPILED_DIR"]).parent / "cwe" / "audit.json"
        if cwe_path.is_file():
            import json as _json
            entries = _json.loads(cwe_path.read_text())
            app._cwe_list = [{"id": e["id"], "name": e["name"]} for e in entries]
        else:
            app._cwe_list = []
    return app._cwe_list


def register_standards_routes(app: Flask) -> None:
    @app.get("/api/standards/refs/cwe")
    def list_cwes() -> Response:
        return jsonify(_load_cwe_list(app))

    @app.get("/api/standards")
    def list_standards() -> Response:
        svc = _get_service(app)
        return jsonify([to_camel_dict(s) for s in svc.list_standards()])

    @app.get("/api/standards/library")
    def list_library() -> Response:
        library = _get_library_client(app)
        if library is None:
            return jsonify([])
        try:
            index = library.fetch_index()
        except Exception as exc:
            logger.warning("Failed to fetch library index: %s", exc)
            return error_response("Failed to connect to standards library", 502, "library_error")
        return jsonify(index)

    @app.post("/api/standards/library/import")
    def import_from_library() -> tuple[Response, int]:
        library = _get_library_client(app)
        if library is None:
            return error_response("Standards library not configured", 400, "library_not_configured")
        payload = request.get_json(force=True)
        file_path = payload.get("file")
        if not file_path:
            return error_response("file is required", 400, "bad_request")
        try:
            library.import_standard(file_path, Path(app.config["STANDARDS_EVALUATORS_DIR"]))
        except ValueError as exc:
            return error_response(str(exc), 409, "conflict")
        except Exception as exc:
            logger.warning("Failed to import standard: %s", exc)
            return error_response(f"Import failed: {exc}", 502, "import_error")
        return jsonify({"status": "imported"}), 201

    @app.get("/api/standards/<standard_id>")
    def get_standard(standard_id: str) -> Response:
        svc = _get_service(app)
        try:
            detail = svc.get_standard(standard_id)
        except FileNotFoundError:
            return error_response(f"Standard not found: {standard_id}", 404, "not_found")
        return jsonify(to_camel_dict(detail))

    @app.post("/api/standards")
    def create_standard() -> tuple[Response, int]:
        svc = _get_service(app)
        payload = request.get_json(force=True)
        try:
            detail = svc.create_standard(payload)
        except ValueError as exc:
            return error_response(str(exc), 400, "bad_request")
        return jsonify(to_camel_dict(detail)), 201

    @app.put("/api/standards/<standard_id>")
    def update_standard(standard_id: str) -> Response:
        svc = _get_service(app)
        payload = request.get_json(force=True)
        try:
            detail = svc.update_standard(standard_id, payload)
        except FileNotFoundError:
            return error_response(f"Standard not found: {standard_id}", 404, "not_found")
        except PermissionError as exc:
            return error_response(str(exc), 403, "forbidden")
        return jsonify(to_camel_dict(detail))

    @app.delete("/api/standards/<standard_id>")
    def delete_standard(standard_id: str) -> tuple[str, int]:
        svc = _get_service(app)
        try:
            svc.delete_standard(standard_id)
        except FileNotFoundError:
            return error_response(f"Standard not found: {standard_id}", 404, "not_found")
        except PermissionError as exc:
            return error_response(str(exc), 403, "forbidden")
        return "", 204

    @app.post("/api/standards/<standard_id>/duplicate")
    def duplicate_standard(standard_id: str) -> tuple[Response, int]:
        svc = _get_service(app)
        payload = request.get_json(force=True)
        new_id = payload.get("newId") or payload.get("new_id")
        if not new_id:
            return error_response("newId is required", 400, "bad_request")
        try:
            detail = svc.duplicate_standard(standard_id, new_id)
        except (FileNotFoundError, ValueError) as exc:
            return error_response(str(exc), 400, "bad_request")
        return jsonify(to_camel_dict(detail)), 201
