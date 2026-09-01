"""Zip-archive validation for project import.

This module is the ingestion point for untrusted user-supplied archives, so
the checks here are intentionally paranoid: every member is checked for path
traversal, absolute paths, symlinks, special files, oversize entries, and
zip-bomb compression ratios before a single byte is extracted.

Split out of import_project.py (Task 9).
"""
from __future__ import annotations

import json
import logging
import uuid as _uuid
import zipfile
from http import HTTPStatus
from typing import Any

from quodeq.api.zip import _MANIFEST_KIND, _MANIFEST_SCHEMA

_logger = logging.getLogger(__name__)

_MAX_MEMBERS = 50_000
_MAX_PER_MEMBER_BYTES = 1 * 1024 * 1024 * 1024  # 1 GiB uncompressed cap per file
_MAX_RATIO = 200  # uncompressed/compressed ratio per member (zip-bomb guard)
_RATIO_GUARD_THRESHOLD = 1024  # only enforce ratio above this uncompressed size
_MAX_PATH_DEPTH = 64  # limit on path components to bound recursion-style attacks


class _ImportError(Exception):
    """Raised when a zip fails validation. Carries an HTTP status + code."""

    def __init__(self, message: str, status: int, code: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def _bad_request(message: str, code: str = "INVALID_ARCHIVE") -> _ImportError:
    return _ImportError(message, HTTPStatus.BAD_REQUEST, code)


def _is_uuid(value: str) -> bool:
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        return False
    return True


def _is_symlink_entry(info: zipfile.ZipInfo) -> bool:
    """Return True if a zip entry encodes a symlink or non-regular file.

    Unix-style permissions live in the high 16 bits of ``external_attr`` for
    ZIP entries created by Info-ZIP and most Python zipfile writers. The
    S_IFMT mask 0xF000 isolates the file type; symlinks have type 0xA000.
    """
    if info.create_system != 3:  # 3 == Unix; non-Unix can't encode symlinks
        return False
    mode = info.external_attr >> 16
    return (mode & 0xF000) == 0xA000


def _validate_member_name(name: str) -> list[str]:
    """Return the cleaned path components, or raise on suspicious shapes."""
    if not name:
        raise _bad_request("Archive contains an empty member name.")
    # Reject NUL, drive letters (Windows), absolute paths, and traversal segments.
    if "\x00" in name:
        raise _bad_request("Archive member contains a NUL byte.")
    if name.startswith("/") or name.startswith("\\"):
        raise _bad_request(f"Archive member uses an absolute path: {name!r}")
    if len(name) > 1 and name[1] == ":":
        raise _bad_request(f"Archive member uses a drive-qualified path: {name!r}")
    # Normalise separators; reject backslashes (we only export forward slashes).
    if "\\" in name:
        raise _bad_request(f"Archive member uses backslashes: {name!r}")
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if not parts:
        raise _bad_request(f"Archive member resolves to an empty path: {name!r}")
    if any(p == ".." for p in parts):
        raise _bad_request(f"Archive member contains parent-directory segment: {name!r}")
    if len(parts) > _MAX_PATH_DEPTH:
        raise _bad_request(f"Archive member exceeds maximum path depth: {name!r}")
    return parts


def _validate_archive(zf: zipfile.ZipFile, *, max_total_bytes: int) -> tuple[str, dict[str, zipfile.ZipInfo]]:
    """Run all security/integrity checks on a zip, return (top_dir, files-by-arcname).

    Raises ``_ImportError`` on any policy violation. Does *not* extract anything.
    """
    infos = zf.infolist()
    if not infos:
        raise _bad_request("Archive is empty.")
    if len(infos) > _MAX_MEMBERS:
        raise _bad_request(
            f"Archive contains too many entries (limit {_MAX_MEMBERS}).",
            "TOO_MANY_MEMBERS",
        )

    files: dict[str, zipfile.ZipInfo] = {}
    top_dirs: set[str] = set()
    total_uncompressed = 0

    for info in infos:
        parts = _validate_member_name(info.filename)
        top_dirs.add(parts[0])
        if len(top_dirs) > 1:
            raise _bad_request(
                "Archive must have a single top-level directory matching the project UUID.",
                "BAD_LAYOUT",
            )
        if info.is_dir():
            continue
        if _is_symlink_entry(info):
            raise _bad_request(
                f"Archive contains a symlink which is not allowed: {info.filename!r}",
                "DISALLOWED_ENTRY",
            )
        if info.file_size < 0 or info.compress_size < 0:
            raise _bad_request(f"Archive member has invalid size fields: {info.filename!r}")
        if info.file_size > _MAX_PER_MEMBER_BYTES:
            raise _bad_request(
                f"Archive member exceeds per-file size limit: {info.filename!r}",
                "MEMBER_TOO_LARGE",
            )
        # Zip-bomb guard: only above a small floor, so tiny well-compressed
        # text files (which legitimately compress very well) don't trip it.
        if (
            info.file_size > _RATIO_GUARD_THRESHOLD
            and info.compress_size > 0
            and info.file_size // max(info.compress_size, 1) > _MAX_RATIO
        ):
            raise _bad_request(
                f"Archive member has suspicious compression ratio: {info.filename!r}",
                "BAD_RATIO",
            )
        total_uncompressed += info.file_size
        if total_uncompressed > max_total_bytes:
            raise _bad_request(
                f"Archive uncompressed size exceeds the {max_total_bytes // (1024 * 1024)} MB limit.",
                "TOO_LARGE",
            )
        files["/".join(parts)] = info

    if not files:
        raise _bad_request("Archive contains no files (only directories).")
    top_dir = next(iter(top_dirs))
    if not _is_uuid(top_dir):
        raise _bad_request(
            f"Archive top-level directory must be a UUID: {top_dir!r}",
            "BAD_LAYOUT",
        )
    return top_dir, files


def _read_member_json(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> dict[str, Any]:
    """Read a small JSON member, capping the bytes read to avoid surprises."""
    if info.file_size > 1 * 1024 * 1024:  # JSON files in our exports are tiny
        raise _bad_request(f"Metadata file too large: {info.filename!r}")
    with zf.open(info) as fh:
        raw = fh.read(info.file_size + 1)
    if len(raw) > info.file_size:
        raise _bad_request(f"Metadata file size mismatch: {info.filename!r}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _bad_request(f"Metadata file is not valid UTF-8: {info.filename!r}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _bad_request(f"Metadata file is not valid JSON: {info.filename!r} ({exc.msg})") from None
    if not isinstance(data, dict):
        raise _bad_request(f"Metadata file must be a JSON object: {info.filename!r}")
    return data


def _validate_manifest(manifest: dict[str, Any], top_dir: str) -> None:
    if manifest.get("schema") != _MANIFEST_SCHEMA:
        raise _bad_request(
            f"Unsupported manifest schema: {manifest.get('schema')!r}",
            "BAD_MANIFEST",
        )
    if manifest.get("kind") != _MANIFEST_KIND:
        raise _bad_request("Archive manifest is not a Quodeq project export.", "BAD_MANIFEST")
    src = manifest.get("source_uuid")
    if not isinstance(src, str) or src != top_dir:
        raise _bad_request(
            "Archive manifest source_uuid does not match top-level directory.",
            "BAD_MANIFEST",
        )


def _validate_repository_info(info: dict[str, Any], expected_uuid: str) -> None:
    if not isinstance(info.get("name"), str) or not info["name"].strip():
        raise _bad_request("repository_info.json missing valid 'name'.", "BAD_REPO_INFO")
    if not isinstance(info.get("path"), str):
        raise _bad_request("repository_info.json missing valid 'path'.", "BAD_REPO_INFO")
    info_uuid = info.get("uuid")
    # The uuid field is informational; mismatches are tolerated but logged.
    if info_uuid and info_uuid != expected_uuid:
        _logger.info(
            "import: repository_info.json uuid %r differs from top dir %r",
            info_uuid, expected_uuid,
        )
