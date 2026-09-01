"""Pull-a-shared-project-locally route.

Split out of routes_shared.py (Task 9). This is a deliberate, spec-approved
exception to the read-only invariant documented in routes_shared.py's module
docstring: it mutates LOCAL state (the local reports directory, via
import_zip_stream), not the shared repository clone itself. The clone is
only read from to build the in-memory zip. It is therefore intentionally
included in the allowed-mutations set of the read-only sweep test
(tests/api/test_routes_shared_read.py::test_no_mutating_routes_under_shared).
"""
from __future__ import annotations

import zipfile
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.api.import_project import import_zip_stream
from quodeq.api.zip import _build_project_zip

from .routes_common import reports_dir
from .routes_shared_common import _logger, _shared_project_dir, _validate_segment, _with_shared_root


def register_shared_pull_routes(app: Flask) -> None:
    @app.post("/api/shared/projects/<project>/pull")
    @_with_shared_root
    def shared_pull(project: str, eval_root: Path, url: str) -> Response | tuple[Response, int]:
        """Materialize a shared project as a local copy.

        Body: optional JSON ``{"action": "copy"|"replace"}`` to resolve a 409
        collision returned from a previous attempt -- same semantics as the
        manual ``POST /api/projects/import`` route, since both funnel through
        ``import_zip_stream``.
        """
        err = _validate_segment(project)
        if err:
            return err
        project_path = _shared_project_dir(eval_root, project)
        if project_path is None:
            body, status = error_response(
                "Project not found in the shared repository", HTTPStatus.NOT_FOUND, "NOT_FOUND",
            )
            return jsonify(body), status

        payload = request.get_json(silent=True) or {}
        action = payload.get("action")
        if action is not None and not isinstance(action, str):
            body, status = error_response("action must be a string", HTTPStatus.BAD_REQUEST, "INVALID_ACTION")
            return jsonify(body), status

        try:
            zip_path = _build_project_zip(project_path)
        except ValueError:
            body, status = error_response(
                "Project too large to pull", HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "TOO_LARGE",
            )
            return jsonify(body), status
        except (OSError, zipfile.BadZipFile):
            _logger.exception("Failed to build zip for shared pull of %s", project)
            body, status = error_response(
                "Failed to build project archive from the shared repository",
                HTTPStatus.INTERNAL_SERVER_ERROR, "EXPORT_ERROR",
            )
            return jsonify(body), status

        try:
            with zip_path.open("rb") as stream:
                outcome = import_zip_stream(
                    stream, reports_dir(), action, remote_addr=request.remote_addr,
                )
            return jsonify(outcome.body), outcome.status
        except OSError:
            _logger.exception("Failed to read zip for shared pull of %s", project)
            body, status = error_response(
                "Failed to read project archive from the shared repository",
                HTTPStatus.INTERNAL_SERVER_ERROR, "EXPORT_ERROR",
            )
            return jsonify(body), status
        finally:
            try:
                zip_path.unlink()
            except OSError as exc:
                _logger.warning("Failed to remove temp zip %s: %s", zip_path, exc)
