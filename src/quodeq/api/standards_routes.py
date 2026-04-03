"""API routes for the Standards Browser & Editor.

Entry point that delegates to focused sub-modules:
- standards_read_routes: GET / list / detail endpoints
- standards_import_routes: import from file and library
- standards_crud_routes: create, update, delete, duplicate
"""
from __future__ import annotations

from pathlib import Path

from flask import Flask

from quodeq.api.standards_crud_routes import register_crud_routes
from quodeq.api.standards_import_routes import register_import_routes
from quodeq.api.standards_read_routes import register_read_routes
from quodeq.services.standards import StandardsService


def _get_service(app: Flask) -> StandardsService:
    """Return the lazily-initialized StandardsService for this Flask app.

    Lifecycle: the ``_standards_service`` attribute is created on first
    request and reused for the lifetime of the Flask app.  Tests can
    pre-set ``app._standards_service`` before any route runs to inject a
    mock or stub, bypassing the real filesystem entirely.
    """
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


def register_standards_routes(app: Flask) -> None:
    register_read_routes(app, _get_service, _get_library_client)
    register_import_routes(app, _get_service, _get_library_client)
    register_crud_routes(app, _get_service)
