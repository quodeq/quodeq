"""Zip export helpers for the action API."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path

from flask import Response, after_this_request, jsonify, send_file

from quodeq.api.helpers import error_response

_logger = logging.getLogger(__name__)

_DEFAULT_MAX_ZIP_SIZE_MB = 500
_MANIFEST_FILENAME = "manifest.json"
_MANIFEST_KIND = "quodeq-project-export"
_MANIFEST_SCHEMA = 1
# Import allows the extracted (uncompressed) archive to reach the MB cap times
# this multiple (evaluation data is text that deflates ~5x). Export applies the
# same bound so it never produces an archive that would fail re-import.
_EXTRACT_HEADROOM = 10


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


def _build_manifest(project_path: Path) -> dict[str, object]:
    """Build the export manifest payload from a project's repository_info.json."""
    from quodeq import __version__ as _qd_version

    info: dict[str, object] = {}
    info_path = project_path / "repository_info.json"
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            info = {}
    return {
        "schema": _MANIFEST_SCHEMA,
        "kind": _MANIFEST_KIND,
        "source_uuid": info.get("uuid") or project_path.name,
        "project_name": info.get("name"),
        "scope_path": info.get("scopePath"),
        "location": info.get("location"),
        "repo_path": info.get("path"),
        "remote_url": info.get("remote_url"),
        "discipline": info.get("discipline"),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "quodeq_version": _qd_version,
    }


def _zip_size_errors(size_limit: int, uncompressed_limit: int) -> tuple[ValueError, ValueError]:
    """Build the (compressed, uncompressed) over-limit errors for these caps."""
    compressed_error = ValueError(
        f"Project exceeds maximum export size of {size_limit // (1024 * 1024)} MB compressed. "
        f"Reduce the project size or increase QUODEQ_MAX_ZIP_SIZE_MB."
    )
    uncompressed_error = ValueError(
        f"Project exceeds maximum uncompressed size of "
        f"{uncompressed_limit // (1024 * 1024)} MB (it would be rejected on re-import). "
        f"Reduce the project size or increase QUODEQ_MAX_ZIP_SIZE_MB."
    )
    return compressed_error, uncompressed_error


def _write_project_zip_entries(
    zf: zipfile.ZipFile, fh, project_path: Path, size_limit: int, uncompressed_limit: int,
    compressed_error: ValueError, uncompressed_error: ValueError,
) -> None:
    """Write every file under *project_path* plus the manifest into *zf*.

    Raises *compressed_error*/*uncompressed_error* the moment either running
    total crosses its cap, so a too-large project fails fast mid-write.
    """
    total_uncompressed = 0
    for file_entry in project_path.rglob("*"):
        if file_entry.is_symlink():
            continue
        if not file_entry.is_file():
            continue
        # Skip any prior manifest so the export-time one is authoritative.
        if file_entry == project_path / _MANIFEST_FILENAME:
            continue
        zf.write(file_entry, file_entry.relative_to(project_path.parent))
        total_uncompressed += file_entry.stat().st_size
        if fh.tell() > size_limit:
            raise compressed_error
        if total_uncompressed > uncompressed_limit:
            raise uncompressed_error
    manifest_json = json.dumps(_build_manifest(project_path), indent=2)
    manifest_arcname = f"{project_path.name}/{_MANIFEST_FILENAME}"
    zf.writestr(manifest_arcname, manifest_json)
    total_uncompressed += len(manifest_json.encode("utf-8"))
    if total_uncompressed > uncompressed_limit:
        raise uncompressed_error


def _build_project_zip(project_path: Path) -> Path:
    """Create a temporary zip archive of a project directory and return its path.

    Two caps mirror the import side so a successful export always re-imports:
    the compressed archive against the MB limit, and the total uncompressed size
    against that limit times ``_EXTRACT_HEADROOM``.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="quodeq_export_")
    os.close(fd)
    size_limit = _max_zip_size_bytes()
    uncompressed_limit = size_limit * _EXTRACT_HEADROOM
    compressed_error, uncompressed_error = _zip_size_errors(size_limit, uncompressed_limit)
    try:
        with open(tmp_path, "wb") as fh:
            with zipfile.ZipFile(fh, "w", zipfile.ZIP_DEFLATED) as zf:
                _write_project_zip_entries(
                    zf, fh, project_path, size_limit, uncompressed_limit,
                    compressed_error, uncompressed_error,
                )
        # The central directory is written on close; re-check the final size.
        if os.path.getsize(tmp_path) > size_limit:
            raise compressed_error
    except (OSError, zipfile.BadZipFile, ValueError):
        os.unlink(tmp_path)
        raise
    return Path(tmp_path)


def export_project_zip(project: str, reports_dir: str) -> Response | tuple[Response, int]:
    """Build and return a zip archive download response for a project directory."""
    project_path = (Path(reports_dir) / project).resolve()
    if not project_path.is_relative_to(Path(reports_dir).resolve()):
        body, status = error_response(
            "Invalid project name. Use only alphanumeric characters, hyphens, and underscores (no path separators).",
            HTTPStatus.BAD_REQUEST, "BAD_REQUEST",
        )
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
        body, status = error_response(
            "Failed to build project archive. Check disk space and file permissions, then try again.",
            HTTPStatus.INTERNAL_SERVER_ERROR, "EXPORT_ERROR",
        )
        return jsonify(body), status

    @after_this_request
    def _cleanup(response: Response) -> Response:
        try:
            os.unlink(str(tmp_path))
        except OSError as exc:
            _logger.warning("Failed to remove temp zip %s: %s", tmp_path, exc)
        return response

    return send_file(str(tmp_path), mimetype="application/zip", as_attachment=True, download_name=f"{project}.zip")
