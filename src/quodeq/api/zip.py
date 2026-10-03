"""Zip export route adapter for the action API.

The archive itself is built in services/project_archive_export.py; this module
resolves the project, maps build failures to coded JSON errors, and streams
the download.
"""
from __future__ import annotations

import logging
import os
import zipfile
from http import HTTPStatus
from pathlib import Path

from flask import Response, after_this_request, send_file

from quodeq.api._constants import CODE_NOT_FOUND
from quodeq.api.helpers import json_error
from quodeq.services.project_archive_export import ExportSizeLimitError, build_project_zip
from quodeq.services.project_archive_format import (  # noqa: F401 -- re-exported for callers and tests
    MANIFEST_KIND,
    MANIFEST_SCHEMA,
    max_zip_size_bytes,
)
from quodeq.shared.constants import MANIFEST_FILENAME  # noqa: F401 -- re-exported for tests

_logger = logging.getLogger(__name__)


def _resolve_project_path(project: str, reports_dir: str) -> tuple[Path | None, tuple[Response, int] | None]:
    """Locate *project* under *reports_dir*. Returns ``(path, None)`` or ``(None, error)``."""
    project_path = (Path(reports_dir) / project).resolve()
    if not project_path.is_relative_to(Path(reports_dir).resolve()):
        return None, json_error(
            "Invalid project name. Use only alphanumeric characters, hyphens, and underscores (no path separators).",
            HTTPStatus.BAD_REQUEST, "BAD_REQUEST",
        )
    if not project_path.exists() or not project_path.is_dir():
        return None, json_error("Project not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
    return project_path, None


def _unlink_after_response(tmp_path: Path) -> None:
    """Remove the temporary archive once the download response has been sent."""
    @after_this_request
    def _cleanup(response: Response) -> Response:
        try:
            os.unlink(str(tmp_path))
        except OSError as exc:
            _logger.warning("Failed to remove temp zip %s: %s", tmp_path, exc)
        return response


def export_project_zip(project: str, reports_dir: str) -> Response | tuple[Response, int]:
    """Build and return a zip archive download response for a project directory."""
    project_path, err = _resolve_project_path(project, reports_dir)
    if err is not None:
        return err
    try:
        tmp_path = build_project_zip(project_path)
    except ExportSizeLimitError as exc:
        return json_error(exc.public_message, HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "TOO_LARGE")
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        # ValueError covers zipfile's own rejections (for example "ZIP does
        # not support timestamps before 1980" from zf.write under the
        # default strict_timestamps=True). Without this they would leave the
        # route as Flask's default 500 page, which carries no code. The
        # message is fixed and the exception only logged, never echoed.
        _logger.warning("Failed to build export zip for %s: %s", project, exc)
        return json_error(
            "Failed to build project archive. Check disk space and file permissions, then try again.",
            HTTPStatus.INTERNAL_SERVER_ERROR, "EXPORT_ERROR",
        )
    _unlink_after_response(tmp_path)
    return send_file(str(tmp_path), mimetype="application/zip", as_attachment=True, download_name=f"{project}.zip")
