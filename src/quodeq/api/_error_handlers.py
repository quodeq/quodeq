"""App-wide fallback for exceptions no route caught.

Route handlers narrow their own catches to the failure types they realize
can happen (OSError, ValueError, sqlite3.Error, ...) and answer a coded
JSON error for those. Anything outside that narrow tuple is a real bug, and
is left to escape the route on purpose (R-FT-7) rather than being papered
over locally. Without this handler that escape reaches Flask's own default
handling, which answers a plain HTML 500 with no machine-readable ``code``
-- every other error response in this API carries one
(tools/check_error_codes.py). This registers ONE handler, for the whole
app, that gives that same case a JSON body instead.
"""
from __future__ import annotations

import logging
from http import HTTPStatus

from flask import Flask, Response
from werkzeug.exceptions import HTTPException

from quodeq.api._constants import CODE_INTERNAL_ERROR
from quodeq.api.helpers import json_error

_logger = logging.getLogger(__name__)


def register_unhandled_error_handler(app: Flask) -> None:
    """Turn an exception no route handled into the standard {"error",
    "code"} body instead of Flask's default HTML error page.

    HTTPException (404, 400, 405, ...) passes through unchanged: Flask
    already gives those their correct status and body. Anything else is
    logged here with its traceback (Flask's own automatic logging never
    runs once a handler intercepts the exception) and answered with a
    fixed, generic message -- never the exception's own text
    (tests/api/test_no_exception_echo.py).
    """
    @app.errorhandler(Exception)
    def _handle_unexpected_error(exc: Exception) -> Response | tuple[Response, int] | HTTPException:
        if isinstance(exc, HTTPException):
            return exc
        _logger.error("Unhandled exception while serving a request", exc_info=exc)
        return json_error(
            "An unexpected error occurred.", HTTPStatus.INTERNAL_SERVER_ERROR, CODE_INTERNAL_ERROR,
        )
