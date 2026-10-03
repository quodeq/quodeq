"""Build a project's export archive on disk.

Walks the project directory, writes each file plus a fresh manifest into a
temporary zip, and enforces the same size caps the import side applies, so a
successful export always re-imports. The HTTP adapter lives in api/zip.py.
"""
from __future__ import annotations

import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from quodeq.services.fs_project_helpers import read_project_record
from quodeq.services.project_archive_format import (
    EXTRACT_HEADROOM,
    MANIFEST_KIND,
    MANIFEST_SCHEMA,
    max_zip_size_bytes,
)
from quodeq.shared.clock import utc_now_iso
from quodeq.shared.constants import MANIFEST_FILENAME
from quodeq.shared.errors import ClientMessageError


def _build_manifest(project_path: Path) -> dict[str, object]:
    """Build the export manifest payload from a project's repository_info.json."""
    from quodeq import __version__ as _qd_version

    info: dict[str, object] = read_project_record(project_path) or {}
    return {
        "schema": MANIFEST_SCHEMA,
        "kind": MANIFEST_KIND,
        "source_uuid": info.get("uuid") or project_path.name,
        "project_name": info.get("name"),
        "scope_path": info.get("scopePath"),
        "location": info.get("location"),
        "repo_path": info.get("path"),
        "remote_url": info.get("remote_url"),
        "discipline": info.get("discipline"),
        "exported_at": utc_now_iso(),
        "quodeq_version": _qd_version,
    }


class ExportSizeLimitError(ClientMessageError, ValueError):
    """Raised when a zip export crosses its compressed or uncompressed size cap.

    Subclasses ValueError so the existing ``except (..., ValueError)`` guards
    around zip building still catch it, but gives the upload route a precise
    type to key off of: the route wants to surface *this* error's own
    actionable message (it carries the MB limits and the remediation), not a
    generic one, without risking that treatment for an unrelated ValueError.

    ``public_message`` comes from ClientMessageError: the route reads that
    attribute rather than ``str(exc)`` so the response never depends on
    exception formatting.
    """


@dataclass(frozen=True)
class _ZipLimits:
    """Size caps for one zip export, plus the errors raised when either is crossed."""

    size_limit: int
    uncompressed_limit: int
    compressed_error: ExportSizeLimitError
    uncompressed_error: ExportSizeLimitError

    @staticmethod
    def build(size_limit: int, uncompressed_limit: int) -> "_ZipLimits":
        """Build a _ZipLimits with the (compressed, uncompressed) over-limit errors for these caps."""
        compressed_error = ExportSizeLimitError(
            f"Project exceeds maximum export size of {size_limit // (1024 * 1024)} MB compressed. "
            f"Reduce the project size or increase QUODEQ_MAX_ZIP_SIZE_MB."
        )
        uncompressed_error = ExportSizeLimitError(
            f"Project exceeds maximum uncompressed size of "
            f"{uncompressed_limit // (1024 * 1024)} MB (it would be rejected on re-import). "
            f"Reduce the project size or increase QUODEQ_MAX_ZIP_SIZE_MB."
        )
        return _ZipLimits(size_limit, uncompressed_limit, compressed_error, uncompressed_error)


def _iter_export_files(project_path: Path):
    """Yield the regular files under *project_path* that belong in the export.

    Symlinks and non-files are skipped, as is any prior manifest so the
    export-time one is authoritative.
    """
    for file_entry in project_path.rglob("*"):
        if file_entry.is_symlink() or not file_entry.is_file():
            continue
        if file_entry == project_path / MANIFEST_FILENAME:
            continue
        yield file_entry


def _write_manifest_entry(zf: zipfile.ZipFile, project_path: Path) -> int:
    """Write the export manifest into *zf*; returns its uncompressed byte size."""
    manifest_json = json.dumps(_build_manifest(project_path), indent=2)
    zf.writestr(f"{project_path.name}/{MANIFEST_FILENAME}", manifest_json)
    return len(manifest_json.encode("utf-8"))


def _write_project_zip_entries(
    zf: zipfile.ZipFile, fh, project_path: Path, limits: _ZipLimits,
) -> None:
    """Write every file under *project_path* plus the manifest into *zf*.

    Raises *limits.compressed_error*/*limits.uncompressed_error* the moment
    either running total crosses its cap, so a too-large project fails fast
    mid-write.
    """
    total_uncompressed = 0
    for file_entry in _iter_export_files(project_path):
        zf.write(file_entry, file_entry.relative_to(project_path.parent))
        total_uncompressed += file_entry.stat().st_size
        if fh.tell() > limits.size_limit:
            raise limits.compressed_error
        if total_uncompressed > limits.uncompressed_limit:
            raise limits.uncompressed_error
    total_uncompressed += _write_manifest_entry(zf, project_path)
    if total_uncompressed > limits.uncompressed_limit:
        raise limits.uncompressed_error


def build_project_zip(project_path: Path) -> Path:
    """Create a temporary zip archive of a project directory and return its path.

    Two caps mirror the import side so a successful export always re-imports:
    the compressed archive against the MB limit, and the total uncompressed size
    against that limit times ``EXTRACT_HEADROOM``.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="quodeq_export_")
    os.close(fd)
    size_limit = max_zip_size_bytes()
    uncompressed_limit = size_limit * EXTRACT_HEADROOM
    limits = _ZipLimits.build(size_limit, uncompressed_limit)
    try:
        with open(tmp_path, "wb") as fh:
            with zipfile.ZipFile(fh, "w", zipfile.ZIP_DEFLATED) as zf:
                _write_project_zip_entries(zf, fh, project_path, limits)
        # The central directory is written on close; re-check the final size.
        if os.path.getsize(tmp_path) > size_limit:
            raise limits.compressed_error
    except (OSError, zipfile.BadZipFile, ValueError):
        os.unlink(tmp_path)
        raise
    return Path(tmp_path)
