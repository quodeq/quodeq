"""Project import: unpack a previously-exported project zip back into reports_dir.

This is the ingestion point for untrusted user-supplied archives, so the
validation is intentionally paranoid: every member is checked for path
traversal, absolute paths, symlinks, special files, oversize entries, and
zip-bomb compression ratios before a single byte is extracted (see
_project_import_validation.py and _project_import_extract.py for the checks).

Framework-free: ``import_zip_stream`` returns a plain ``ImportOutcome`` that
the HTTP layer (api/import_project.py, api/routes_shared_pull.py) turns into
a response. Collaborators:
  - project_import_identity.py: identity-collision detection and index updates.
  - _project_import_extract.py: ``safe_extract``, the hardened extraction step.
  - _project_import_upload.py: ``open_upload``, the bounded view of the upload.
  - _project_import_validation.py: archive/member/manifest/repo-info validation.
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

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.services.project_archive_format import EXTRACT_HEADROOM, max_zip_size_bytes
from quodeq.services.project_import_identity import (
    REPO_INFO_FILENAME,
    find_identity_collision,
    identity_from_info,
    rewrite_repository_info,
    update_index,
)
from quodeq.services.project_index import ProjectIdentity
from quodeq.shared.constants import MANIFEST_FILENAME
from quodeq.shared.errors import CODE_INVALID_ACTION, CODE_PROJECT_EXISTS

from ._project_import_extract import StrandedBackupError, safe_extract, swap_into_place
from ._project_import_upload import open_upload
from ._project_import_validation import (
    ImportOutcome,
    ImportValidationError,
    bad_request,
    read_member_json,
    validate_archive,
    validate_manifest,
    validate_member_name,
    validate_repository_info,
)

_ACTION_REPLACE = "replace"
_ACTION_COPY = "copy"
IMPORT_ACTIONS = frozenset({_ACTION_REPLACE, _ACTION_COPY})
IO_ERROR_CODE = "IO_ERROR"
IO_ERROR_MESSAGE = "Failed to write imported project. Check disk space and permissions."

_KIND_SAME_UUID = "same_uuid"  # the archive's project UUID is already on disk
_KIND_SAME_IDENTITY = "same_identity"  # another project has the same repo identity


def error_outcome(message: str, status: int, code: str) -> ImportOutcome:
    """An ``ImportOutcome`` carrying the standard ``{"error", "code"}`` error body."""
    return ImportOutcome(status, {"error": message, "code": code})


def _project_exists(message: str, kind: str, existing_id: str, identity: ProjectIdentity) -> ImportOutcome:
    """The 409 that asks the client to choose copy or replace for a collision."""
    outcome = error_outcome(message, HTTPStatus.CONFLICT, CODE_PROJECT_EXISTS)
    outcome.body.update(kind=kind, existingProjectId=existing_id, projectName=identity.project_name)
    return outcome


def _resolve_import_conflict(
    reports_root: Path, top_dir: str, action: str | None, identity: ProjectIdentity, log: LogSink,
) -> tuple[str, bool] | ImportOutcome:
    """Resolve a UUID or identity collision for an incoming import.

    Returns ``(target_uuid, replace_existing)``, or an ``ImportOutcome`` (a
    CONFLICT or the AMBIGUOUS_REPLACE error) for the caller to return
    immediately. Deletes nothing: a replace swaps the old project out only
    once the new one is extracted (see ``_stage_and_commit``).
    """
    same_uuid_path = reports_root / top_dir
    same_uuid_collision = same_uuid_path.is_dir()
    same_identity_uuid = find_identity_collision(reports_root, identity, ignore_uuid=top_dir, log=log)

    # Without an explicit action, surface the collision so the client can
    # prompt the user.
    if same_uuid_collision:
        if action == _ACTION_REPLACE:
            return top_dir, True
        if action == _ACTION_COPY:
            return str(_uuid.uuid4()), False
        return _project_exists("Project already exists", _KIND_SAME_UUID, top_dir, identity)
    if same_identity_uuid is not None:
        if action == _ACTION_COPY:
            # No UUID collision, so the incoming UUID is fine: both
            # projects coexist (different UUIDs, same repo identity).
            return top_dir, False
        if action == _ACTION_REPLACE:
            # 'replace' on identity collision is ambiguous (two UUIDs for
            # the same repo). Refuse rather than guess.
            return error_outcome(
                "Cannot replace: a different project with the same repo identity already exists. "
                "Use 'copy' to import as a separate project.",
                HTTPStatus.CONFLICT, "AMBIGUOUS_REPLACE",
            )
        return _project_exists(
            "A project for this repository already exists", _KIND_SAME_IDENTITY, same_identity_uuid, identity,
        )
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
    zf: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo], target: _ImportTarget, log: LogSink,
) -> None:
    """Extract into a staging dir, set the target UUID in the staged
    repository_info.json, atomically rename into place, then update the
    project index.

    The rename is the commit point: a failure before it leaves no project
    directory and removes the staging dir; after it the project is complete
    and only the best-effort index update remains.
    """
    staging = Path(tempfile.mkdtemp(prefix="quodeq_import_", dir=str(target.reports_root)))
    keep_staging = False  # set when the staging dir holds the only copy of the old project
    try:
        safe_extract(zf, members, staging)
        staged_project = staging / target.top_dir
        if not staged_project.is_dir():
            raise bad_request("Archive missing top-level project directory.", "BAD_LAYOUT")
        if target.target_uuid != target.top_dir and not rewrite_repository_info(
            staged_project, target.target_uuid, log=log,
        ):
            raise OSError(f"could not set uuid {target.target_uuid} in the staged {REPO_INFO_FILENAME}")
        final_path = target.reports_root / target.target_uuid
        if target.replace_existing and final_path.exists():
            swap_into_place(staged_project, final_path, staging, log=log)
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

    update_index(target.reports_root, target.identity, target.target_uuid, log=log)


def _read_and_validate_member_payloads(
    zf: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo], top_dir: str, log: LogSink,
) -> dict[str, Any]:
    """Read + validate the required repository_info.json and optional
    manifest.json members; return the parsed repository_info dict."""
    repo_info_arc = f"{top_dir}/{REPO_INFO_FILENAME}"
    if repo_info_arc not in members:
        raise bad_request(f"Archive missing required {REPO_INFO_FILENAME}.", "MISSING_REPO_INFO")
    repo_info = read_member_json(zf, members[repo_info_arc])
    validate_repository_info(repo_info, top_dir, log=log)

    manifest_arc = f"{top_dir}/{MANIFEST_FILENAME}"
    if manifest_arc in members:
        manifest = read_member_json(zf, members[manifest_arc])
        validate_manifest(manifest, top_dir)

    return repo_info


def _build_success_outcome(
    target: _ImportTarget, action: str | None, remote_addr: str | None, log: LogSink,
) -> ImportOutcome:
    log.info(
        f"import_project: source_uuid={target.top_dir} target_uuid={target.target_uuid} "
        f"action={action} remote_addr={remote_addr}"
    )
    return ImportOutcome(HTTPStatus.OK, {
        "imported": True,
        "projectId": target.target_uuid,
        "sourceProjectId": target.top_dir,
        "renamed": target.target_uuid != target.top_dir,
        "projectName": target.identity.project_name,
    })


def _plan_import(
    zf: zipfile.ZipFile, reports_root: Path, action: str | None, size_limit: int, log: LogSink,
) -> tuple[_ImportTarget, dict[str, zipfile.ZipInfo]] | ImportOutcome:
    """Validate the archive and resolve where it lands, or the collision outcome."""
    # An OSError reading the archive here is not caught: it propagates as a
    # read failure, not the write failure of ``_commit_import``.
    top_dir, members = validate_archive(zf, max_total_bytes=size_limit * EXTRACT_HEADROOM)
    repo_info = _read_and_validate_member_payloads(zf, members, top_dir, log)
    identity = identity_from_info(repo_info)
    resolution = _resolve_import_conflict(reports_root, top_dir, action, identity, log)
    if isinstance(resolution, ImportOutcome):
        return resolution
    target_uuid, replace_existing = resolution
    return _ImportTarget(reports_root, top_dir, target_uuid, identity, replace_existing), members


def _commit_import(
    zf: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo], target: _ImportTarget, log: LogSink,
) -> ImportOutcome | None:
    """Materialize *target*; a filesystem failure becomes the IO_ERROR outcome."""
    try:
        _stage_and_commit(zf, members, target, log)
    except OSError as exc:
        log.warning(f"import: filesystem error: {exc}")
        return error_outcome(IO_ERROR_MESSAGE, HTTPStatus.INTERNAL_SERVER_ERROR, IO_ERROR_CODE)
    return None


def _import_archive(
    upload: Any, reports_root: Path, action: str | None, size_limit: int, log: LogSink,
) -> _ImportTarget | ImportOutcome:
    """Open *upload* as a zip and import it; bad archives become 400 outcomes."""
    try:
        with zipfile.ZipFile(upload) as zf:
            plan = _plan_import(zf, reports_root, action, size_limit, log)
            if isinstance(plan, ImportOutcome):
                return plan
            target, members = plan
            return _commit_import(zf, members, target, log) or target
    except ImportValidationError as exc:
        return error_outcome(exc.public_message, exc.status, exc.code)
    except zipfile.BadZipFile:
        return error_outcome("File is not a valid zip archive.", HTTPStatus.BAD_REQUEST, "BAD_ZIP")


def _import_upload(
    upload: Any, reports_dir: str, action: str | None, size_limit: int, log: LogSink,
) -> _ImportTarget | ImportOutcome:
    """Check the upload size and reports dir, then import the archive."""
    if upload is None:
        return error_outcome(
            f"Archive exceeds the {size_limit // (1024 * 1024)} MB import limit.",
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "TOO_LARGE",
        )
    reports_root = Path(reports_dir).resolve()
    if not reports_root.is_dir():
        return error_outcome("reports directory does not exist", HTTPStatus.INTERNAL_SERVER_ERROR, "NO_REPORTS_DIR")
    return _import_archive(upload, reports_root, action, size_limit, log)


def import_zip_stream(
    stream: Any, reports_dir: str, action: str | None, *,
    remote_addr: str | None = None, log: LogSink = NULL_LOG,
) -> ImportOutcome:
    """Validate and materialize a project zip *stream* into *reports_dir*.

    *stream* needs ``.read(n)``; a seekable one is sized in place (see
    ``_project_import_upload.open_upload``). Returns a plain
    :class:`ImportOutcome`. *action* is ``"replace"``/``"copy"`` to resolve a
    409 collision; *remote_addr* is only for the audit log.
    """
    if action is not None and action not in IMPORT_ACTIONS:
        return error_outcome(
            f"Invalid action; expected one of {sorted(IMPORT_ACTIONS)}.",
            HTTPStatus.BAD_REQUEST, CODE_INVALID_ACTION,
        )
    size_limit = max_zip_size_bytes()
    with open_upload(stream, size_limit) as upload:
        result = _import_upload(upload, reports_dir, action, size_limit, log)
    if isinstance(result, ImportOutcome):
        return result
    return _build_success_outcome(result, action, remote_addr, log)


__all__ = [
    "IO_ERROR_CODE",
    "IO_ERROR_MESSAGE",
    "ImportOutcome",
    "ImportValidationError",
    "error_outcome",
    "import_zip_stream",
    "validate_member_name",
]
