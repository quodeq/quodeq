"""register_project's two steps: resolve the project's identity/slot, then
materialize it on disk and scan.

Split out of ``project_registration.py`` (Task 22, M-MOD-6): that module sits
at the 300-line size ratchet, so these steps live here instead. This module
imports only downward (``_wiring``, ``_fs_clone``, ``_fs_scan``,
``_registration_scan``, ``_registration_url``, ``shared``) and never imports
back from ``project_registration`` -- ``project_registration.py`` imports it
at the top instead. ``_resolve_target_path``, ``_persist_repository_info``,
and ``_ensure_onboarding_field`` moved here too (they had no remaining
callers left in ``project_registration.py``); tests that patch the I/O they
call (``run_git_clone``, ``validate_remote_url``, ``write_repository_info``)
target ``quodeq.services._project_registration_steps.<name>`` now.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.services._fs_clone import run_git_clone
from quodeq.services._fs_scan import scan_project
from quodeq.services._registration_scan import _scan_parent_project
from quodeq.services._registration_url import _read_origin_remote, _strip_credentials
from quodeq.services._wiring import (
    ProjectIdentity,
    read_repository_info,
    resolve_project_uuid,
    validate_remote_url,
    write_repository_info,
)
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
        # Re-validate immediately before the clone dispatch: the project-uuid
        # resolution between _validate_clone_target's check and here (index
        # load, legacy directory scan, project creation) does real disk I/O and
        # can take enough wall-clock time for a DNS-rebinding attacker to flip
        # the host from a public to a private IP. This narrows, but does not
        # close, the race -- git clone re-resolves DNS again itself, independently,
        # inside the subprocess below; only pinning the resolved IP through git's
        # own connection (a hosts-file override or proxy layer) would close it,
        # and that's out of scope here.
        validate_remote_url(repo)
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


def _ensure_onboarding_field(project_dir: Path) -> None:
    """Add `onboardingCompletedAt: null` to repository_info.json if absent.

    Called during registration (via `_resolve_project_slot`) so newly-registered
    projects start with the field set to null. Existing projects without the
    field get a backfill on read (see `_backfill_onboarding_field` in
    _fs_project_helpers.py).
    """
    data = read_repository_info(project_dir)
    if data is None or "onboardingCompletedAt" in data:
        return
    data["onboardingCompletedAt"] = None
    write_repository_info(project_dir, data)


def _resolve_project_slot(
    repo: str, discipline: str | None, reports_path: Path, scope_path: str | None,
) -> tuple[str, Path, str, str]:
    """Resolve project identity/uuid/dir. Returns
    (project_uuid, project_dir, project_name, repo_resolved)."""
    is_url = is_repo_url(repo)
    project_name = project_name_from_repo(repo)
    repo_resolved = repo if is_url else str(Path(repo).resolve())

    project_uuid = resolve_project_uuid(
        reports_path,
        ProjectIdentity(project_name, repo_resolved, discipline, _LOCATION_LOCAL, scope_path=scope_path),
    )
    project_dir = reports_path / project_uuid
    _ensure_onboarding_field(project_dir)
    return project_uuid, project_dir, project_name, repo_resolved


@dataclass(frozen=True)
class _MaterializeRequest:
    """Everything ``_materialize_and_scan`` needs, bundled to keep its own
    parameter count down."""

    repo: str
    repo_resolved: str
    project_name: str
    project_uuid: str
    project_dir: Path
    reports_path: Path
    scope_path: str | None
    is_url: bool
    ephemeral: bool
    clone_dest: str | None
    clones_dir: Path | None
    log: LogSink = NULL_LOG


def _materialize_and_scan(request: _MaterializeRequest) -> None:
    """Resolve the on-disk path, persist repository_info.json, and scan."""
    target_path = _resolve_target_path(
        request.repo, request.repo_resolved, request.project_name, request.project_uuid,
        is_url=request.is_url, ephemeral=request.ephemeral,
        clone_dest=request.clone_dest, clones_dir=request.clones_dir,
    )
    _persist_repository_info(
        request.project_dir, target_path,
        is_url=request.is_url, repo=request.repo, ephemeral=request.ephemeral,
    )

    # Scan now that files are guaranteed on disk.
    scan_project(target_path, output_dir=request.project_dir)
    if request.scope_path:
        _scan_parent_project(request.project_dir, request.reports_path, target_path, log=request.log)
