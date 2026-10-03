"""``POST /api/projects/import``: the HTTP side of project import.

Parses the multipart request and turns the plain ``ImportOutcome`` from
``quodeq.services.project_import.import_zip_stream`` into a Flask response.
The validation, extraction and index update live in that service.
"""
from __future__ import annotations

import logging
from http import HTTPStatus

from flask import Response, jsonify, request

from quodeq.api.helpers import json_error
from quodeq.services.project_import import (
    IO_ERROR_CODE,
    IO_ERROR_MESSAGE,
    error_outcome,
    import_zip_stream,
)
from quodeq.shared.log_sink import LoggerSink

logger = logging.getLogger(__name__)
# The import service logs through an injected sink; this routes it to the
# module logger above.
IMPORT_LOG = LoggerSink(logger)


def import_project(reports_dir: str) -> Response | tuple[Response, int]:
    """Handle ``POST /api/projects/import``.

    Body: ``multipart/form-data`` with:
        - ``file``: the project zip (required)
        - ``action``: optional, ``"replace"`` or ``"copy"`` to resolve a 409
          collision returned from a previous attempt.

    Parses the multipart request for file and action parameters, then
    delegates validation and extraction to ``import_zip_stream`` and converts
    its plain ``ImportOutcome`` to a Flask response, the single place this
    route touches ``jsonify``. Maps an uncaught ``OSError`` to the IO_ERROR
    response too, since not every failure inside ``import_zip_stream`` is one.
    """
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return json_error("file is required", HTTPStatus.BAD_REQUEST, "MISSING_FILE")

    action = (request.form.get("action") or "").strip().lower() or None
    try:
        outcome = import_zip_stream(
            upload, reports_dir, action, remote_addr=request.remote_addr, log=IMPORT_LOG,
        )
    except OSError as exc:
        logger.warning("import: filesystem error: %s", exc)
        outcome = error_outcome(IO_ERROR_MESSAGE, HTTPStatus.INTERNAL_SERVER_ERROR, IO_ERROR_CODE)
    return jsonify(outcome.body), outcome.status


__all__ = ["import_project"]
