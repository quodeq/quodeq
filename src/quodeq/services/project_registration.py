"""Use case: register a project (resolve identity, clone if needed, scan).

Extracted from ``evaluation_mixin`` so the API layer has a public entry
point instead of importing private helpers.

Split (Task 12) into two sibling modules plus this orchestrator:
  - _registration_url.py: credential-stripping and origin-remote reads.
  - _registration_scan.py: the zero-run scan fallback and parent-project scan.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.services._wiring import (
    ProjectIdentity,
    read_repository_info,
    resolve_project_uuid,
    validate_remote_url,
    write_repository_info,
)
from quodeq.services._fs_clone import CloneError, run_git_clone
from quodeq.services._fs_project_helpers import find_existing_project
from quodeq.services._fs_scan import scan_project
from quodeq.services._registration_scan import _scan_parent_project, _zero_run_scan_fallback
from quodeq.services._registration_url import _read_origin_remote, _strip_credentials
from quodeq.services.base import CreateProjectResult, NewProjectSpec
from quodeq.shared._env import get_clones_dir
from quodeq.shared.utils import is_repo_url, project_name_from_repo

_LOCATION_LOCAL = "local"


def _resolve_target_path(
    repo: str, repo_resolved: str, project_name: str, project_uuid: str, *,
    is_url: bool, ephemeral: bool, clone_dest: str | None, clones_dir: Path | None,
) -> Path:
    """Resolve/create the on-disk path the project will live at.

    For a URL input, clones into an ephemeral cache dir or the caller's
    chosen *clone_dest*. For a local path input, resolves in place -- the
    directory must already exist.
    """
    if is_url:
        if ephemeral:
            target_path = (clones_dir or get_clones_dir()) / project_uuid
        else:
            target_path = Path(clone_dest).resolve() / project_name
        target_path.parent.mkdir(parents=True, exist_ok=True)
        # run_git_clone raises CloneError on failure (Task A8). We let it propagate.
        run_git_clone(repo, target_path)
        return target_path

    target_path = Path(repo_resolved)
    if not target_path.is_dir():
        # A path pointing at a FILE is a distinct user mistake from a
        # missing path (a real registration once slipped through as
        # .../lib/player.js) — say which one it was.
        detail = "points at a file, not a directory" if target_path.exists() else "does not exist"
        raise FileNotFoundError(f"Repo path {detail}: {target_path}")
    return target_path


def _persist_repository_info(
    project_dir: Path, target_path: Path, *, is_url: bool, repo: str, ephemeral: bool,
) -> None:
    """Persist the resolved path + ephemeral flag in repository_info.json.

    A corrupt existing file is treated as empty and rewritten (self-heal);
    registration is the flow that owns this file's creation.
    """
    info = read_repository_info(project_dir) or {}
    info["path"] = str(target_path.resolve())
    info["location"] = _LOCATION_LOCAL
    info["ephemeral"] = bool(ephemeral)
    origin_url = repo if is_url else _read_origin_remote(target_path)
    if origin_url:
        # Defense in depth: _read_origin_remote already strips credentials
        # from the local-remote branch, but strip again here so the
        # URL-registration branch (raw *repo*) is covered too, and so this
        # call site stays safe even if the helper's behavior changes.
        info["originUrl"] = _strip_credentials(origin_url)
    write_repository_info(project_dir, info)


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
    repo: str,
    discipline: str | None,
    reports_dir: str,
    scope_path: str | None = None,
    *,
    clone_dest: str | None = None,
    ephemeral: bool = False,
    clones_dir: Path | None = None,
) -> str:
    """Resolve/register project and run a scan.

    For URL inputs, clones the repo before scanning. Either *clone_dest* (a
    user-chosen parent directory) or *ephemeral=True* must be set when *repo*
    is a URL. Ephemeral clones land under ``~/.quodeq/clones/<uuid>/`` by
    default; pass *clones_dir* to use a different (already-resolved) base
    directory instead of re-reading QUODEQ_CLONES_DIR here.

    For local path inputs, scans in place; *clone_dest* and *ephemeral* are
    ignored.

    Returns the project's UUID.
    """
    is_url = is_repo_url(repo)
    _validate_clone_target(repo, is_url, ephemeral, clone_dest)

    project_name = project_name_from_repo(repo)
    repo_resolved = repo if is_url else str(Path(repo).resolve())
    reports_path = Path(reports_dir)

    project_uuid = resolve_project_uuid(
        reports_path,
        ProjectIdentity(project_name, repo_resolved, discipline, _LOCATION_LOCAL, scope_path=scope_path),
    )
    project_dir = reports_path / project_uuid
    _ensure_onboarding_field(project_dir)

    target_path = _resolve_target_path(
        repo, repo_resolved, project_name, project_uuid,
        is_url=is_url, ephemeral=ephemeral, clone_dest=clone_dest, clones_dir=clones_dir,
    )
    _persist_repository_info(project_dir, target_path, is_url=is_url, repo=repo, ephemeral=ephemeral)

    # Scan now that files are guaranteed on disk.
    scan_project(target_path, output_dir=project_dir)
    if scope_path:
        _scan_parent_project(project_dir, reports_path, target_path)

    return project_uuid


def _ensure_onboarding_field(project_dir: Path) -> None:
    """Add `onboardingCompletedAt: null` to repository_info.json if absent.

    Called from `register_project` so newly-registered projects start with the
    field set to null. Existing projects without the field get a backfill on
    read (see `_backfill_onboarding_field` in _fs_project_helpers.py).
    """
    data = read_repository_info(project_dir)
    if data is None or "onboardingCompletedAt" in data:
        return
    data["onboardingCompletedAt"] = None
    write_repository_info(project_dir, data)


def _rollback_new_dirs(reports_root: str, before: set[str]) -> None:
    """Delete any project directories created since *before* was captured."""
    reports_path = Path(reports_root)
    if not reports_path.is_dir():
        return
    after = {p.name for p in reports_path.iterdir() if p.is_dir()}
    for new in after - before:
        try:
            shutil.rmtree(reports_path / new, ignore_errors=True)
        except OSError:
            pass


def _rollback_and_report(
    reports_dir: str, before: set[str], status: str, message: str = "", **extra,
) -> CreateProjectResult:
    """Roll back any partial project dirs and build the failure result."""
    _rollback_new_dirs(reports_dir, before)
    return CreateProjectResult(status=status, message=message, **extra)


def _snapshot_project_dirs(reports_path: Path) -> set[str]:
    """Names of project dirs present before registration, so a failed
    scan/clone can be rolled back to exactly what existed before."""
    return {p.name for p in reports_path.iterdir() if p.is_dir()} if reports_path.is_dir() else set()


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
        return CreateProjectResult(status="duplicate", existing_project_id=existing)

    reports_root_path = Path(reports_dir)
    before = _snapshot_project_dirs(reports_root_path)

    try:
        project_uuid = register_project(
            spec.repo,
            spec.discipline,
            reports_dir,
            scope_path=spec.scope_path,
            clone_dest=spec.clone_dest,
            ephemeral=spec.ephemeral,
            clones_dir=clones_dir,
        )
    except (FileNotFoundError, ValueError) as exc:
        return _rollback_and_report(reports_dir, before, "invalid_repo", str(exc))
    except CloneError as exc:
        return _rollback_and_report(
            reports_dir, before, "clone_failed", str(exc), clone_error_kind=exc.kind,
        )
    except Exception as exc:
        # error_response (route layer) swallows the traceback Flask's own 500
        # handler would have logged; record it before converting to a
        # generic, no-detail result (the exception text can carry filesystem
        # paths or backend internals that must not reach the remote caller).
        log.error(f"Registration failed for repo={spec.repo!r}: {exc}")
        return _rollback_and_report(reports_dir, before, "internal_error")

    # scan.json is now always present after register_project succeeds.
    scan_path = reports_root_path / project_uuid / "scan.json"
    try:
        scan_data = json.loads(scan_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, FileNotFoundError):
        scan_data = _zero_run_scan_fallback()
    return CreateProjectResult(status="created", project_id=project_uuid, scan_data=scan_data)


def mark_onboarding_complete(project_dir: Path) -> None:
    """Stamp `onboardingCompletedAt` in repository_info.json if not already set.

    An existing timestamp is left untouched so re-evaluations don't move the
    original completion time.
    """
    data = read_repository_info(project_dir)
    if data is None or data.get("onboardingCompletedAt"):
        return
    data["onboardingCompletedAt"] = datetime.now(timezone.utc).isoformat()
    write_repository_info(project_dir, data)
