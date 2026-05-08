"""Project import: unpack a previously-exported project zip back into reports_dir.

This module is the ingestion point for untrusted user-supplied archives, so the
validation here is intentionally paranoid: every member is checked for path
traversal, absolute paths, symlinks, special files, oversize entries, and
zip-bomb compression ratios before a single byte is extracted.
"""
from __future__ import annotations

import io
import json
import logging
import shutil
import tempfile
import uuid as _uuid
import zipfile
from http import HTTPStatus
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.api.zip import (
    _MANIFEST_FILENAME,
    _MANIFEST_KIND,
    _MANIFEST_SCHEMA,
    _max_zip_size_bytes,
)
from quodeq.data.fs._index_io import _load_index, _save_index
from quodeq.data.fs._models import ProjectIdentity
from quodeq.data.fs._resolution import _index_key

_logger = logging.getLogger(__name__)

_REPO_INFO_FILENAME = "repository_info.json"
_MAX_MEMBERS = 50_000
_MAX_PER_MEMBER_BYTES = 1 * 1024 * 1024 * 1024  # 1 GiB uncompressed cap per file
_MAX_RATIO = 200  # uncompressed/compressed ratio per member (zip-bomb guard)
_RATIO_GUARD_THRESHOLD = 1024  # only enforce ratio above this uncompressed size
_MAX_PATH_DEPTH = 64  # limit on path components to bound recursion-style attacks

_ACTION_REPLACE = "replace"
_ACTION_COPY = "copy"
_ALLOWED_ACTIONS = frozenset({_ACTION_REPLACE, _ACTION_COPY})


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


def _identity_from_info(info: dict[str, Any]) -> ProjectIdentity:
    return ProjectIdentity(
        project_name=str(info.get("name") or ""),
        repo_path=str(info.get("path") or ""),
        discipline=info.get("discipline") if isinstance(info.get("discipline"), str) else None,
        location=str(info.get("location") or "local"),
        scope_path=info.get("scopePath") if isinstance(info.get("scopePath"), str) else None,
        remote_url=info.get("remote_url") if isinstance(info.get("remote_url"), str) else None,
    )


def _find_identity_collision(reports_root: Path, identity: ProjectIdentity, *, ignore_uuid: str) -> str | None:
    """Walk existing projects to see if any other UUID matches this identity.

    Mirrors ``routes_project_list._find_existing_project`` but takes a
    ``ProjectIdentity`` directly and ignores the candidate UUID being imported.
    """
    if not reports_root.is_dir():
        return None
    for child in reports_root.iterdir():
        if not child.is_dir() or child.name == ignore_uuid:
            continue
        info_file = child / _REPO_INFO_FILENAME
        if not info_file.exists():
            continue
        try:
            data = json.loads(info_file.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("name") != identity.project_name:
            continue
        if data.get("path") != identity.repo_path:
            continue
        if (data.get("scopePath") or None) != (identity.scope_path or None):
            continue
        return child.name
    return None


def _safe_extract(zf: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo], dest: Path) -> None:
    """Extract validated members into *dest*, double-checking each target path."""
    dest_resolved = dest.resolve()
    for arcname, info in members.items():
        target = (dest / arcname).resolve()
        if target != dest_resolved and not target.is_relative_to(dest_resolved):
            raise _bad_request(f"Archive member would escape target dir: {arcname!r}", "PATH_ESCAPE")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst, length=64 * 1024)


def _rewrite_repository_info(project_dir: Path, new_uuid: str) -> None:
    """Update the imported project's repository_info.json with its new UUID."""
    info_path = project_dir / _REPO_INFO_FILENAME
    try:
        data = json.loads(info_path.read_text())
    except (OSError, json.JSONDecodeError):
        return
    data["uuid"] = new_uuid
    try:
        info_path.write_text(json.dumps(data, indent=2))
    except OSError as exc:
        _logger.warning("import: could not rewrite repository_info.json: %s", exc)


def _update_index(reports_root: Path, identity: ProjectIdentity, project_uuid: str) -> None:
    """Best-effort: register the imported project in project_index.json."""
    try:
        index = _load_index(reports_root)
        index[_index_key(identity)] = project_uuid
        _save_index(reports_root, index)
    except OSError as exc:
        _logger.warning("import: could not update project_index.json: %s", exc)


def import_project(reports_dir: str) -> Response | tuple[Response, int]:
    """Handle ``POST /api/projects/import``.

    Body: ``multipart/form-data`` with:
        - ``file``: the project zip (required)
        - ``action``: optional, ``"replace"`` or ``"copy"`` to resolve a 409
          collision returned from a previous attempt.
    """
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        body, status = error_response("file is required", HTTPStatus.BAD_REQUEST, "MISSING_FILE")
        return jsonify(body), status

    action = (request.form.get("action") or "").strip().lower() or None
    if action is not None and action not in _ALLOWED_ACTIONS:
        body, status = error_response(
            f"Invalid action; expected one of {sorted(_ALLOWED_ACTIONS)}.",
            HTTPStatus.BAD_REQUEST, "INVALID_ACTION",
        )
        return jsonify(body), status

    size_limit = _max_zip_size_bytes()
    raw = upload.read(size_limit + 1)
    if len(raw) > size_limit:
        body, status = error_response(
            f"Archive exceeds the {size_limit // (1024 * 1024)} MB import limit.",
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "TOO_LARGE",
        )
        return jsonify(body), status

    reports_root = Path(reports_dir).resolve()
    if not reports_root.is_dir():
        body, status = error_response("reports directory does not exist", HTTPStatus.INTERNAL_SERVER_ERROR, "NO_REPORTS_DIR")
        return jsonify(body), status

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            top_dir, members = _validate_archive(zf, max_total_bytes=size_limit)

            repo_info_arc = f"{top_dir}/{_REPO_INFO_FILENAME}"
            if repo_info_arc not in members:
                raise _bad_request(
                    f"Archive missing required {_REPO_INFO_FILENAME}.",
                    "MISSING_REPO_INFO",
                )
            repo_info = _read_member_json(zf, members[repo_info_arc])
            _validate_repository_info(repo_info, top_dir)

            manifest_arc = f"{top_dir}/{_MANIFEST_FILENAME}"
            if manifest_arc in members:
                manifest = _read_member_json(zf, members[manifest_arc])
                _validate_manifest(manifest, top_dir)

            identity = _identity_from_info(repo_info)
            same_uuid_path = reports_root / top_dir
            same_uuid_collision = same_uuid_path.is_dir()
            same_identity_uuid = _find_identity_collision(
                reports_root, identity, ignore_uuid=top_dir,
            )

            # Conflict resolution. Without an explicit action, surface the
            # collision so the client can prompt the user.
            target_uuid = top_dir
            if same_uuid_collision:
                if action == _ACTION_REPLACE:
                    shutil.rmtree(same_uuid_path, ignore_errors=False)
                elif action == _ACTION_COPY:
                    target_uuid = str(_uuid.uuid4())
                else:
                    return jsonify({
                        "error": "Project already exists",
                        "code": "PROJECT_EXISTS",
                        "kind": "same_uuid",
                        "existingProjectId": top_dir,
                        "projectName": identity.project_name,
                    }), HTTPStatus.CONFLICT
            elif same_identity_uuid is not None:
                if action == _ACTION_COPY:
                    # No UUID collision, so the incoming UUID is fine — both
                    # projects coexist (different UUIDs, same repo identity).
                    target_uuid = top_dir
                elif action == _ACTION_REPLACE:
                    # 'replace' on identity collision is ambiguous (two UUIDs
                    # for the same repo). Refuse rather than guess.
                    body, status = error_response(
                        "Cannot replace: a different project with the same repo identity already exists. "
                        "Use 'copy' to import as a separate project.",
                        HTTPStatus.CONFLICT, "AMBIGUOUS_REPLACE",
                    )
                    return jsonify(body), status
                else:
                    return jsonify({
                        "error": "A project for this repository already exists",
                        "code": "PROJECT_EXISTS",
                        "kind": "same_identity",
                        "existingProjectId": same_identity_uuid,
                        "projectName": identity.project_name,
                    }), HTTPStatus.CONFLICT

            # Stage the extraction in a sibling tmpdir so commit is a single rename.
            staging = Path(tempfile.mkdtemp(prefix="quodeq_import_", dir=str(reports_root)))
            try:
                _safe_extract(zf, members, staging)
                staged_project = staging / top_dir
                if not staged_project.is_dir():
                    raise _bad_request("Archive missing top-level project directory.", "BAD_LAYOUT")
                final_path = reports_root / target_uuid
                if final_path.exists():  # extremely narrow race window after the replace check above
                    raise _bad_request("Target project directory already exists.", "RACE")
                staged_project.rename(final_path)
            finally:
                shutil.rmtree(staging, ignore_errors=True)

            if target_uuid != top_dir:
                _rewrite_repository_info(final_path, target_uuid)

            _update_index(reports_root, identity, target_uuid)

    except _ImportError as exc:
        body, status = error_response(str(exc), exc.status, exc.code)
        return jsonify(body), status
    except zipfile.BadZipFile:
        body, status = error_response(
            "File is not a valid zip archive.",
            HTTPStatus.BAD_REQUEST, "BAD_ZIP",
        )
        return jsonify(body), status
    except OSError as exc:
        _logger.warning("import: filesystem error: %s", exc)
        body, status = error_response(
            "Failed to write imported project. Check disk space and permissions.",
            HTTPStatus.INTERNAL_SERVER_ERROR, "IO_ERROR",
        )
        return jsonify(body), status

    _logger.info(
        "import_project: source_uuid=%s target_uuid=%s action=%s remote_addr=%s",
        top_dir, target_uuid, action, request.remote_addr,
    )
    return jsonify({
        "imported": True,
        "projectId": target_uuid,
        "sourceProjectId": top_dir,
        "renamed": target_uuid != top_dir,
        "projectName": identity.project_name,
    })


# Re-export for routing module.
__all__ = ["import_project"]
