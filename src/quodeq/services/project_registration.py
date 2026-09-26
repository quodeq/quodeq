"""Use case: register a project (resolve identity, clone if needed, scan).

The API layer's public entry point for registration. This orchestrator
works with two sibling modules:
  - _registration_url.py: credential-stripping and origin-remote reads.
  - _registration_scan.py: the zero-run scan fallback and parent-project scan.
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Callable

from quodeq.shared.clock import utc_now_iso
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.services.wiring import (
    list_project_dirs,
    read_repository_info,
    read_scan_json,
    remove_project_dir,
    validate_remote_url,
    write_repository_info,
)
from quodeq.services._fs_clone import CloneError
from quodeq.services.fs_project_helpers import find_existing_project
from quodeq.services._registration_scan import zero_run_scan_fallback
from quodeq.services._project_registration_steps import (
    MaterializeRequest,
    materialize_and_scan,
    resolve_project_slot,
)
from quodeq.services._repo_index import RepoIdentity, add_repo_index_entry
from quodeq.services.base import CreateProjectResult, CreateProjectStatus, NewProjectSpec
from quodeq.shared.utils import is_repo_url


def _validate_clone_target(
    repo: str, is_url: bool, ephemeral: bool, clone_dest: str | None,
) -> None:
    """Validate repo/clone_dest before any clone or directory side effects."""
    if is_url:
        # SSRF guard: reject private/loopback/link-local hosts before any clone
        # or directory side effects. Mirrors the CLI prepare_repository path so
        # the web API (POST /api/projects) cannot be pointed at internal hosts.
        validate_remote_url(repo)
    if is_url and not ephemeral and clone_dest is None:
        raise ValueError(
            "URL repos require either clone_dest (user-chosen path) or ephemeral=True"
        )
    if is_url and not ephemeral:
        dest = Path(clone_dest)
        if not dest.is_dir():
            raise FileNotFoundError(
                f"clone destination does not exist or is not a directory: {clone_dest}"
            )


def register_project(
    reports_dir: str,
    spec: NewProjectSpec,
    *,
    clones_dir: Path | None = None,
    log: LogSink = NULL_LOG,
) -> str:
    """Resolve/register project and run a scan.

    For URL inputs, clones the repo before scanning. Either ``spec.clone_dest``
    (a user-chosen parent directory) or ``spec.ephemeral=True`` must be set
    when ``spec.repo`` is a URL. Ephemeral clones land under *clones_dir*
    (only consulted when ``spec.ephemeral`` is set). This function never
    reads QUODEQ_CLONES_DIR itself: the caller (the provider composing this
    call -- ``FilesystemActionProvider``/``FsEvaluationMixin`` in
    ``filesystem.py``/``evaluation_mixin.py``) resolves the default and
    passes an already-resolved path.

    For local path inputs, scans in place; ``clone_dest`` and ``ephemeral``
    are ignored, and *clones_dir* is never consulted.

    Returns the project's UUID.
    """
    is_url = is_repo_url(spec.repo)
    _validate_clone_target(spec.repo, is_url, spec.ephemeral, spec.clone_dest)
    reports_path = Path(reports_dir)

    project_uuid, project_dir, project_name, repo_resolved = resolve_project_slot(
        spec.repo, spec.discipline, reports_path, spec.scope_path,
    )

    materialize_and_scan(MaterializeRequest(
        repo=spec.repo, repo_resolved=repo_resolved, project_name=project_name,
        project_uuid=project_uuid, project_dir=project_dir, reports_path=reports_path,
        scope_path=spec.scope_path, is_url=is_url, ephemeral=spec.ephemeral,
        clone_dest=spec.clone_dest, clones_dir=clones_dir, log=log,
    ))

    _sync_repo_index_on_create(
        reports_path, RepoIdentity(project_name, repo_resolved, spec.scope_path), project_uuid,
    )
    return project_uuid


def _sync_repo_index_on_create(
    reports_path: Path, identity: RepoIdentity, project_uuid: str,
) -> None:
    """Register this identity in find_existing_project's duplicate-check index.

    Called only once creation has fully succeeded: a failure above is rolled
    back by the caller via plain directory removal, which would leave a
    dangling index entry if this ran any earlier.
    """
    add_repo_index_entry(reports_path, identity, project_uuid)


def _rollback_new_dirs(reports_root: str, before: set[str], *, log: LogSink = NULL_LOG) -> None:
    """Delete any project directories created since *before* was captured."""
    reports_path = Path(reports_root)
    for new in list_project_dirs(reports_path) - before:
        if not remove_project_dir(reports_path / new):
            log.warning(f"registration rollback could not remove {reports_path / new}")


def _rollback_and_report(
    rollback: Callable[[], None], status: CreateProjectStatus, message: str = "", **extra,
) -> CreateProjectResult:
    """Run *rollback*, then build the failure result."""
    rollback()
    return CreateProjectResult(status=status, message=message, **extra)


def _snapshot_project_dirs(reports_path: Path) -> set[str]:
    """Names of project dirs present before registration, so a failed
    scan/clone can be rolled back to exactly what existed before."""
    return list_project_dirs(reports_path)


def register_project_with_rollback(
    reports_dir: str, spec: NewProjectSpec, *,
    clones_dir: Path | None = None, log: LogSink = NULL_LOG,
) -> CreateProjectResult:
    """Register a new project end to end: duplicate check, clone + scan,
    rollback of any partial project directory on failure, scan.json readback.

    The API route keeps its own request-boundary checks (repo-URL shape,
    cloneDest containment, local-path allowlist) and only builds *spec* once
    those pass; this function owns everything downstream of that.
    """
    existing = find_existing_project(reports_dir, spec.repo, spec.scope_path)
    if existing is not None:
        return CreateProjectResult(status=CreateProjectStatus.DUPLICATE, existing_project_id=existing)

    reports_root_path = Path(reports_dir)
    before = _snapshot_project_dirs(reports_root_path)
    rollback = functools.partial(_rollback_new_dirs, reports_dir, before, log=log)

    try:
        project_uuid = register_project(reports_dir, spec, clones_dir=clones_dir, log=log)
    except (FileNotFoundError, ValueError) as exc:
        return _rollback_and_report(rollback, CreateProjectStatus.INVALID_REPO, str(exc))
    except CloneError as exc:
        return _rollback_and_report(
            rollback, CreateProjectStatus.CLONE_FAILED, str(exc), clone_error_kind=exc.kind,
        )
    except Exception:
        # An unhandled failure: clean up any partial project directory, then
        # let it propagate. The app-wide handler in api/_error_handlers.py
        # logs the traceback and answers it with the coded INTERNAL_ERROR.
        rollback()
        raise

    # scan.json is now always present after register_project succeeds.
    project_dir = reports_root_path / project_uuid
    scan_data = read_scan_json(project_dir) or zero_run_scan_fallback()
    return CreateProjectResult(status=CreateProjectStatus.CREATED, project_id=project_uuid, scan_data=scan_data)


def mark_onboarding_complete(project_dir: Path) -> None:
    """Stamp `onboardingCompletedAt` in repository_info.json if not already set.

    An existing timestamp is left untouched so re-evaluations don't move the
    original completion time.
    """
    data = read_repository_info(project_dir)
    if data is None or data.get("onboardingCompletedAt"):
        return
    data["onboardingCompletedAt"] = utc_now_iso()
    write_repository_info(project_dir, data)
