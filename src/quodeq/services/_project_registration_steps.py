"""register_project's two steps: resolve the project's identity/slot, then
materialize it on disk and scan.

Split out of ``project_registration.py`` (Task 22, M-MOD-6): that module sits
at the 300-line size ratchet, so these steps live here instead. Imports back
from ``project_registration`` for the callees it absorbs (``_resolve_target_path``,
``_persist_repository_info``, ``_ensure_onboarding_field``): those stay put
because tests patch the underlying I/O (``run_git_clone``, ``validate_remote_url``,
``write_repository_info``) by ``quodeq.services.project_registration.<name>``,
which only resolves correctly if the callers of those names stay defined
there. ``register_project`` imports this module back with a deferred import
to avoid a circular top-level import between the two.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quodeq.services._fs_scan import scan_project
from quodeq.services._registration_scan import _scan_parent_project
from quodeq.services._wiring import ProjectIdentity, resolve_project_uuid
from quodeq.services.project_registration import (
    _LOCATION_LOCAL,
    _ensure_onboarding_field,
    _persist_repository_info,
    _resolve_target_path,
)
from quodeq.shared.utils import is_repo_url, project_name_from_repo


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
        _scan_parent_project(request.project_dir, request.reports_path, target_path)
