"""Zip export helpers for the action API."""
from __future__ import annotations

import logging
import os
import tempfile
import zipfile
from http import HTTPStatus
from pathlib import Path

from flask import Response, after_this_request, jsonify, send_file

_logger = logging.getLogger(__name__)

from quodeq.api.helpers import error_response

_DEFAULT_MAX_ZIP_SIZE_MB = 500


def _max_zip_size_bytes(max_mb: int | None = None, env: dict[str, str] | None = None) -> int:
    """Return the max zip export size in bytes.

    *max_mb* overrides the env var for testing.
    """
    if max_mb is None:
        raw = (env or os.environ).get("QUODEQ_MAX_ZIP_SIZE_MB")
        if raw is not None:
            try:
                max_mb = int(raw)
            except ValueError:
                max_mb = _DEFAULT_MAX_ZIP_SIZE_MB
        else:
            max_mb = _DEFAULT_MAX_ZIP_SIZE_MB
    return max_mb * 1024 * 1024


def _build_project_zip(project_path: Path) -> Path:
    """Create a temporary zip archive of a project directory and return its path."""
    fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="quodeq_export_")
    os.close(fd)
    total_size = 0
    size_limit = _max_zip_size_bytes()
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_entry in project_path.rglob("*"):
                if file_entry.is_symlink():
                    continue
                if not file_entry.is_file():
                    continue
                total_size += file_entry.stat().st_size
                if total_size > size_limit:
                    raise ValueError("Project exceeds maximum export size")
                zf.write(file_entry, file_entry.relative_to(project_path.parent))
    except (OSError, zipfile.BadZipFile, ValueError):
        os.unlink(tmp_path)
        raise
    return Path(tmp_path)


def export_project_zip(project: str, reports_dir: str) -> Response | tuple[Response, int]:
    """Build and return a zip archive download response for a project directory."""
    project_path = (Path(reports_dir) / project).resolve()
    if not project_path.is_relative_to(Path(reports_dir).resolve()):
        body, status = error_response("Invalid project name", HTTPStatus.BAD_REQUEST, "BAD_REQUEST")
        return jsonify(body), status
    if not project_path.exists() or not project_path.is_dir():
        body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        return jsonify(body), status
    try:
        tmp_path = _build_project_zip(project_path)
    except ValueError:
        body, status = error_response("Project too large to export", HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "TOO_LARGE")
        return jsonify(body), status
    except (OSError, zipfile.BadZipFile):
        body, status = error_response("Failed to build project archive", HTTPStatus.INTERNAL_SERVER_ERROR, "EXPORT_ERROR")
        return jsonify(body), status

    @after_this_request
    def _cleanup(response: Response) -> Response:
        try:
            os.unlink(str(tmp_path))
        except OSError as exc:
            _logger.warning("Failed to remove temp zip %s: %s", tmp_path, exc)
        return response

    return send_file(str(tmp_path), mimetype="application/zip", as_attachment=True, download_name=f"{project}.zip")
