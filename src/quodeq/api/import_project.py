"""Project import: unpack a previously-exported project zip back into reports_dir.

This module is the ingestion point for untrusted user-supplied archives, so the
validation here is intentionally paranoid: every member is checked for path
traversal, absolute paths, symlinks, special files, oversize entries, and
zip-bomb compression ratios before a single byte is extracted (see
_import_validation.py and _import_extract.py for the checks themselves).

Split (Task 9) into three collaborator modules plus this orchestrator:
  - _import_validation.py: archive/member/manifest/repo-info validation.
  - _import_identity.py: identity-collision detection and index updates.
  - _import_extract.py: ``_safe_extract``, the hardened extraction step.
This module re-exports every moved name so existing imports and patches
(tests/api/test_project_import.py) keep working unchanged.
"""
from __future__ import annotations

import io
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
    _EXTRACT_HEADROOM,
    _MANIFEST_FILENAME,
    _max_zip_size_bytes,
)
from quodeq.services.project_index import ProjectIdentity

from ._import_extract import _safe_extract  # noqa: F401 — re-export
from ._import_identity import (
    _REPO_INFO_FILENAME,
    _find_identity_collision,
    _identity_from_info,
    _rewrite_repository_info,  # noqa: F401 — re-export
    _update_index,
)
from ._import_validation import (
    _ImportError,
    _bad_request,
    _is_symlink_entry,  # noqa: F401 — re-export
    _is_uuid,  # noqa: F401 — re-export
    _logger,
    _read_member_json,
    _validate_archive,
    _validate_manifest,
    _validate_member_name,  # noqa: F401 — re-export
    _validate_repository_info,
)

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
) -> str | ImportOutcome:
    """Resolve a UUID or identity collision for an incoming import.

    Returns the UUID to import under, or an ``ImportOutcome`` (a CONFLICT or
    the AMBIGUOUS_REPLACE error) for the caller to return immediately.
    """
    same_uuid_path = reports_root / top_dir
    same_uuid_collision = same_uuid_path.is_dir()
    same_identity_uuid = _find_identity_collision(reports_root, identity, ignore_uuid=top_dir)

    # Without an explicit action, surface the collision so the client can
    # prompt the user.
    if same_uuid_collision:
        if action == _ACTION_REPLACE:
            shutil.rmtree(same_uuid_path, ignore_errors=False)
            return top_dir
        if action == _ACTION_COPY:
            return str(_uuid.uuid4())
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
            return top_dir
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
    return top_dir


def _stage_and_commit(
    zf: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo], reports_root: Path,
    top_dir: str, target_uuid: str, identity: ProjectIdentity,
) -> None:
    """Extract into a staging dir, atomically rename into place, then update
    the repository_info.json UUID (if renamed) and the project index."""
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


def import_zip_stream(
    stream: Any, reports_dir: str, action: str | None, *,
    remote_addr: str | None = None,
) -> ImportOutcome:
    """Validate and materialize a project zip *stream* into *reports_dir*.

    Contains all the hardened validation (path traversal, zip-bomb ratio,
    symlinks, member limits, collision handling) that used to live directly
    in ``import_project``. *stream* is anything with a ``.read(n)`` method
    (a Werkzeug ``FileStorage``, an ``io.BytesIO``, or a plain file handle) —
    this function never touches Flask, so it is callable from any caller that
    already has zip bytes, such as the shared-repo "pull local copy" route.
    It returns a plain :class:`ImportOutcome`; the caller decides how to
    deliver it.

    *action* is optional, ``"replace"`` or ``"copy"`` to resolve a 409
    collision returned from a previous attempt. *remote_addr* is only for the
    success audit log; HTTP callers pass the request's remote address.
    """
    if action is not None and action not in _ALLOWED_ACTIONS:
        return _error_outcome(
            f"Invalid action; expected one of {sorted(_ALLOWED_ACTIONS)}.",
            HTTPStatus.BAD_REQUEST, "INVALID_ACTION",
        )

    size_limit = _max_zip_size_bytes()
    raw = stream.read(size_limit + 1)
    if len(raw) > size_limit:
        return _error_outcome(
            f"Archive exceeds the {size_limit // (1024 * 1024)} MB import limit.",
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "TOO_LARGE",
        )

    reports_root = Path(reports_dir).resolve()
    if not reports_root.is_dir():
        return _error_outcome("reports directory does not exist", HTTPStatus.INTERNAL_SERVER_ERROR, "NO_REPORTS_DIR")

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            top_dir, members = _validate_archive(zf, max_total_bytes=size_limit * _EXTRACT_HEADROOM)

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
            resolution = _resolve_import_conflict(reports_root, top_dir, action, identity)
            if isinstance(resolution, ImportOutcome):
                return resolution
            target_uuid = resolution

            _stage_and_commit(zf, members, reports_root, top_dir, target_uuid, identity)

    except _ImportError as exc:
        return _error_outcome(str(exc), exc.status, exc.code)
    except zipfile.BadZipFile:
        return _error_outcome(
            "File is not a valid zip archive.",
            HTTPStatus.BAD_REQUEST, "BAD_ZIP",
        )
    except OSError as exc:
        _logger.warning("import: filesystem error: %s", exc)
        return _error_outcome(
            "Failed to write imported project. Check disk space and permissions.",
            HTTPStatus.INTERNAL_SERVER_ERROR, "IO_ERROR",
        )

    _logger.info(
        "import_project: source_uuid=%s target_uuid=%s action=%s remote_addr=%s",
        top_dir, target_uuid, action, remote_addr,
    )
    return ImportOutcome(HTTPStatus.OK, {
        "imported": True,
        "projectId": target_uuid,
        "sourceProjectId": top_dir,
        "renamed": target_uuid != top_dir,
        "projectName": identity.project_name,
    })


# Re-export for routing module.
__all__ = ["ImportOutcome", "import_project", "import_zip_stream"]
