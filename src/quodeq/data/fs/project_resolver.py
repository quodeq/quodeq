"""Persistent UUID-based project identity resolution for the reports directory.

Split into focused modules:
- _models: ProjectIdentity, ProjectRepository
- _index_cache: thread-safe mtime cache
- _index_io: load/save index file
- _resolution: find/create project directories
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from quodeq.data.fs._index_cache import clear_index_cache
from quodeq.data.fs._index_io import FilesystemProjectRepository
from quodeq.data.fs._models import ProjectIdentity, ProjectRepository
from quodeq.data.fs._resolution import create_project, find_existing_project
from quodeq.data.fs.children import find_children
from quodeq.core.types.project_source import ProjectLocation

# Re-exports for backward compatibility
__all__ = [
    "ProjectIdentity",
    "ProjectRepository",
    "clear_index_cache",
    "resolve_project_uuid",
]


def _find_or_create(
    reports_dir: Path, identity: ProjectIdentity, repository: ProjectRepository,
    parent_uuid: str | None = None,
) -> str:
    """The project already indexed for *identity*, else a new one under *parent_uuid*."""
    existing = find_existing_project(reports_dir, identity, repository)
    if existing:
        return existing
    return create_project(reports_dir, identity, repository, parent_uuid=parent_uuid)


def _at_path(identity: ProjectIdentity, resolved_path: str, **changes: str | None) -> ProjectIdentity:
    """*identity* at *resolved_path*, unscoped unless *changes* set ``scope_path``."""
    fields: dict[str, str | None] = {"scope_path": None, **changes}
    return replace(identity, repo_path=resolved_path, **fields)


def _resolve_scoped(
    reports_dir: Path, identity: ProjectIdentity, resolved_path: str, repository: ProjectRepository,
) -> str:
    """Resolve a scoped project: ensure parent exists, then resolve child."""
    parent_uuid = _find_or_create(reports_dir, _at_path(identity, resolved_path), repository)
    child_identity = _at_path(
        identity, resolved_path,
        project_name=f"{identity.project_name}/{identity.scope_path}", scope_path=identity.scope_path,
    )
    return _find_or_create(reports_dir, child_identity, repository, parent_uuid)


def _resolve_unscoped(
    reports_dir: Path, identity: ProjectIdentity, resolved_path: str, repository: ProjectRepository,
) -> str:
    """Resolve an unscoped project, creating a dot-child if children exist."""
    resolved = _at_path(identity, resolved_path)
    existing = find_existing_project(reports_dir, resolved, repository)
    if not existing:
        return create_project(reports_dir, resolved, repository)
    if not find_children(reports_dir, existing):
        return existing
    dot_identity = _at_path(
        identity, resolved_path, project_name=f"{identity.project_name}/.", scope_path=".",
    )
    return _find_or_create(reports_dir, dot_identity, repository, existing)


def resolve_project_uuid(
    reports_dir: Path,
    identity: ProjectIdentity,
    repository: ProjectRepository | None = None,
) -> str:
    """Find or create a UUID project directory matching identity.

    When *repository* is provided, it is used for loading/saving the index
    instead of the default filesystem helpers, making the storage layer
    injectable for testing or alternative backends.

    When *identity.scope_path* is set, a parent project (full repo) is
    resolved/created first, then a child project scoped to the subfolder
    is resolved/created with a ``parent`` back-link.
    """
    if identity.location == ProjectLocation.ONLINE:
        resolved_path = identity.repo_path
    else:
        resolved_path = str(Path(identity.repo_path).resolve())
        if not Path(resolved_path).is_absolute():
            raise ValueError(f"Resolved repo path is not absolute: {resolved_path}")

    if not reports_dir.exists():
        reports_dir.mkdir(parents=True, exist_ok=True)

    if repository is None:
        repository = FilesystemProjectRepository()
    if identity.scope_path:
        return _resolve_scoped(reports_dir, identity, resolved_path, repository)
    return _resolve_unscoped(reports_dir, identity, resolved_path, repository)
