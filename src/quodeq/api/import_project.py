"""Project import: unpack a previously-exported project zip back into reports_dir.

This module is the ingestion point for untrusted user-supplied archives, so the
validation here is intentionally paranoid: every member is checked for path
traversal, absolute paths, symlinks, special files, oversize entries, and
zip-bomb compression ratios before a single byte is extracted (see
_import_validation.py and _import_extract.py for the checks themselves).

Split into four collaborator modules plus this orchestrator:
  - _import_validation.py: archive/member/manifest/repo-info validation.
  - _import_identity.py: identity-collision detection and index updates.
  - _import_extract.py: ``safe_extract``, the hardened extraction step.
  - _import_upload.py: ``open_upload``, the bounded view of the uploaded archive.
This module re-exports every moved name so existing imports and patches
(tests/api/test_project_import.py) keep working unchanged.
"""
from __future__ import annotations

import shutil
import tempfile
import uuid as _uuid
import zipfile
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.api.zip import (
    EXTRACT_HEADROOM,
    MANIFEST_FILENAME,
    max_zip_size_bytes,
)
from quodeq.services.project_index import ProjectIdentity

from ._import_extract import StrandedBackupError, safe_extract, swap_into_place  # safe_extract re-exported
from ._import_identity import (
    REPO_INFO_FILENAME,
    find_identity_collision,
    identity_from_info,
    rewrite_repository_info,  # re-export
    update_index,
)
from ._import_validation import (
    ImportValidationError,
    bad_request,
    is_symlink_entry,  # noqa: F401 — re-export
    is_uuid,  # noqa: F401 — re-export
    logger,
    read_member_json,
    validate_archive,
    validate_manifest,
    validate_member_name,  # noqa: F401 — re-export
    validate_repository_info,
)
from ._import_upload import open_upload

_ACTION_REPLACE = "replace"
_ACTION_COPY = "copy"
_ALLOWED_ACTIONS = frozenset({_ACTION_REPLACE, _ACTION_COPY})


@dataclass(frozen=True)
class ImportOutcome:
    """Plain result of :func:`import_zip_stream`: HTTP status + JSON-safe body.

    Framework-free by design — the Flask wrappers (``import_project`` here,
    ``shared_pull`` in routes_shared) convert it via ``jsonify`` exactly once.
    """

    status: int
    body: dict[str, Any]


def _error_outcome(message: str, status: int, code: str) -> ImportOutcome:
    body, http_status = error_response(message, status, code)
    return ImportOutcome(http_status, body)


def import_project(reports_dir: str) -> Response | tuple[Response, int]:
    """Handle ``POST /api/projects/import``.

    Body: ``multipart/form-data`` with:
        - ``file``: the project zip (required)
        - ``action``: optional, ``"replace"`` or ``"copy"`` to resolve a 409
          collision returned from a previous attempt.

    Parses the multipart request for file and action parameters, then
    delegates validation and extraction to ``import_zip_stream`` and converts
    its plain ``ImportOutcome`` to a Flask response — the single place this
    route touches ``jsonify``.
    """
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        body, status = error_response("file is required", HTTPStatus.BAD_REQUEST, "MISSING_FILE")
        return jsonify(body), status

    action = (request.form.get("action") or "").strip().lower() or None
    outcome = import_zip_stream(upload, reports_dir, action, remote_addr=request.remote_addr)
    return jsonify(outcome.body), outcome.status


def _resolve_import_conflict(
    reports_root: Path, top_dir: str, action: str | None, identity: ProjectIdentity,
) -> tuple[str, bool] | ImportOutcome:
    """Resolve a UUID or identity collision for an incoming import.

    Returns ``(target_uuid, replace_existing)``, or an ``ImportOutcome`` (a
    CONFLICT or the AMBIGUOUS_REPLACE error) for the caller to return
    immediately. Deletes nothing: a replace swaps the old project out only
    once the new one is extracted (see ``_stage_and_commit``).
    """
    same_uuid_path = reports_root / top_dir
    same_uuid_collision = same_uuid_path.is_dir()
    same_identity_uuid = find_identity_collision(reports_root, identity, ignore_uuid=top_dir)

    # Without an explicit action, surface the collision so the client can
    # prompt the user.
    if same_uuid_collision:
        if action == _ACTION_REPLACE:
            return top_dir, True
        if action == _ACTION_COPY:
            return str(_uuid.uuid4()), False
        return ImportOutcome(HTTPStatus.CONFLICT, {
            "error": "Project already exists",
            "code": "PROJECT_EXISTS",
            "kind": "same_uuid",
            "existingProjectId": top_dir,
            "projectName": identity.project_name,
        })
    if same_identity_uuid is not None:
        if action == _ACTION_COPY:
            # No UUID collision, so the incoming UUID is fine — both
            # projects coexist (different UUIDs, same repo identity).
            return top_dir, False
        if action == _ACTION_REPLACE:
            # 'replace' on identity collision is ambiguous (two UUIDs for
            # the same repo). Refuse rather than guess.
            return _error_outcome(
                "Cannot replace: a different project with the same repo identity already exists. "
                "Use 'copy' to import as a separate project.",
                HTTPStatus.CONFLICT, "AMBIGUOUS_REPLACE",
            )
        return ImportOutcome(HTTPStatus.CONFLICT, {
            "error": "A project for this repository already exists",
            "code": "PROJECT_EXISTS",
            "kind": "same_identity",
            "existingProjectId": same_identity_uuid,
            "projectName": identity.project_name,
        })
    return top_dir, False


@dataclass(frozen=True, slots=True)
class _ImportTarget:
    """Where an incoming archive lands once its collisions are resolved.

    ``top_dir`` is the UUID directory inside the archive; ``target_uuid`` is
    the directory it is materialized under (differs on a "copy" import).
    """

    reports_root: Path
    top_dir: str
    target_uuid: str
    identity: ProjectIdentity
    replace_existing: bool = False


def _stage_and_commit(
    zf: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo], target: _ImportTarget,
) -> None:
    """Extract into a staging dir, atomically rename into place, then update
    the repository_info.json UUID (if renamed) and the project index."""
    staging = Path(tempfile.mkdtemp(prefix="quodeq_import_", dir=str(target.reports_root)))
    keep_staging = False  # set when the staging dir holds the only copy of the old project
    try:
        safe_extract(zf, members, staging)
        staged_project = staging / target.top_dir
        if not staged_project.is_dir():
            raise bad_request("Archive missing top-level project directory.", "BAD_LAYOUT")
        final_path = target.reports_root / target.target_uuid
        if target.replace_existing and final_path.exists():
            swap_into_place(staged_project, final_path, staging)
        else:
            if final_path.exists():  # extremely narrow race window after the collision check
                raise bad_request("Target project directory already exists.", "RACE")
            staged_project.rename(final_path)
    except StrandedBackupError:
        keep_staging = True
        raise
    finally:
        if not keep_staging:
            shutil.rmtree(staging, ignore_errors=True)

    if target.target_uuid != target.top_dir:
        rewrite_repository_info(final_path, target.target_uuid)

    update_index(target.reports_root, target.identity, target.target_uuid)


def _read_and_validate_member_payloads(
    zf: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo], top_dir: str,
) -> dict[str, Any]:
    """Read + validate the required repository_info.json and optional
    manifest.json members; return the parsed repository_info dict."""
    repo_info_arc = f"{top_dir}/{REPO_INFO_FILENAME}"
    if repo_info_arc not in members:
        raise bad_request(
            f"Archive missing required {REPO_INFO_FILENAME}.",
            "MISSING_REPO_INFO",
        )
    repo_info = read_member_json(zf, members[repo_info_arc])
    validate_repository_info(repo_info, top_dir)

    manifest_arc = f"{top_dir}/{MANIFEST_FILENAME}"
    if manifest_arc in members:
        manifest = read_member_json(zf, members[manifest_arc])
        validate_manifest(manifest, top_dir)

    return repo_info


def _build_success_outcome(
    target: _ImportTarget, action: str | None, remote_addr: str | None,
) -> ImportOutcome:
    logger.info(
        "import_project: source_uuid=%s target_uuid=%s action=%s remote_addr=%s",
        target.top_dir, target.target_uuid, action, remote_addr,
    )
    return ImportOutcome(HTTPStatus.OK, {
        "imported": True,
        "projectId": target.target_uuid,
        "sourceProjectId": target.top_dir,
        "renamed": target.target_uuid != target.top_dir,
        "projectName": target.identity.project_name,
    })


def import_zip_stream(
    stream: Any, reports_dir: str, action: str | None, *,
    remote_addr: str | None = None,
) -> ImportOutcome:
    """Validate and materialize a project zip *stream* into *reports_dir*.

    Framework-free (*stream* needs ``.read(n)``; a seekable one is sized in
    place, see ``_import_upload.open_upload``); returns a plain
    :class:`ImportOutcome`. *action* is ``"replace"``/``"copy"`` to resolve a
    409 collision; *remote_addr* is only for the audit log.
    """
    if action is not None and action not in _ALLOWED_ACTIONS:
        return _error_outcome(
            f"Invalid action; expected one of {sorted(_ALLOWED_ACTIONS)}.",
            HTTPStatus.BAD_REQUEST, "INVALID_ACTION",
        )
    size_limit = max_zip_size_bytes()
    with open_upload(stream, size_limit) as upload:
        if upload is None:
            return _error_outcome(
                f"Archive exceeds the {size_limit // (1024 * 1024)} MB import limit.",
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "TOO_LARGE",
            )
        reports_root = Path(reports_dir).resolve()
        if not reports_root.is_dir():
            return _error_outcome("reports directory does not exist", HTTPStatus.INTERNAL_SERVER_ERROR, "NO_REPORTS_DIR")
        try:
            with zipfile.ZipFile(upload) as zf:
                top_dir, members = validate_archive(zf, max_total_bytes=size_limit * EXTRACT_HEADROOM)
                repo_info = _read_and_validate_member_payloads(zf, members, top_dir)
                identity = identity_from_info(repo_info)
                resolution = _resolve_import_conflict(reports_root, top_dir, action, identity)
                if isinstance(resolution, ImportOutcome):
                    return resolution
                target_uuid, replace_existing = resolution
                target = _ImportTarget(reports_root, top_dir, target_uuid, identity, replace_existing)
                _stage_and_commit(zf, members, target)
        except ImportValidationError as exc:
            return _error_outcome(exc.public_message, exc.status, exc.code)
        except zipfile.BadZipFile:
            return _error_outcome(
                "File is not a valid zip archive.",
                HTTPStatus.BAD_REQUEST, "BAD_ZIP",
            )
        except OSError as exc:
            logger.warning("import: filesystem error: %s", exc)
            return _error_outcome(
                "Failed to write imported project. Check disk space and permissions.",
                HTTPStatus.INTERNAL_SERVER_ERROR, "IO_ERROR",
            )

    return _build_success_outcome(target, action, remote_addr)


# Re-export for routing module.
__all__ = ["ImportOutcome", "import_project", "import_zip_stream"]
