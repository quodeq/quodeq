"""Persistent UUID-based project identity resolution for the reports directory.

Split into focused modules:
- _models: ProjectIdentity, ProjectRepository
- _index_cache: thread-safe mtime cache
- _index_io: load/save index file
- _resolution: find/create project directories
"""
from __future__ import annotations

from pathlib import Path

from quodeq.data.fs._index_cache import clear_index_cache
from quodeq.data.fs._index_io import _load_index, _save_index
from quodeq.data.fs._models import ProjectIdentity, ProjectRepository
from quodeq.data.fs._resolution import _create_project, _find_existing_project

# Re-exports for backward compatibility
__all__ = [
    "ProjectIdentity",
    "ProjectRepository",
    "clear_index_cache",
    "resolve_project_uuid",
]


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
    if identity.location == "online":
        resolved_path = identity.repo_path
    else:
        resolved_path = str(Path(identity.repo_path).resolve())
        # Ensure the resolved local path stays within a real absolute location
        # and hasn't escaped via symlink or traversal.
        if not Path(resolved_path).is_absolute():
            raise ValueError(f"Resolved repo path is not absolute: {resolved_path}")

    if not reports_dir.exists():
        reports_dir.mkdir(parents=True, exist_ok=True)

    load_fn = repository.load_index if repository is not None else _load_index
    save_fn = repository.save_index if repository is not None else _save_index

    # --- scoped resolution: ensure parent exists, then resolve child ---
    if identity.scope_path:
        parent_identity = ProjectIdentity(
            identity.project_name, resolved_path, identity.discipline, identity.location,
        )
        parent_uuid = _find_existing_project(reports_dir, parent_identity, load_fn, save_fn)
        if not parent_uuid:
            parent_uuid = _create_project(reports_dir, parent_identity, load_fn, save_fn)

        child_name = f"{identity.project_name}/{identity.scope_path}"
        child_identity = ProjectIdentity(
            child_name, resolved_path, identity.discipline, identity.location,
            scope_path=identity.scope_path,
        )
        existing = _find_existing_project(reports_dir, child_identity, load_fn, save_fn)
        if existing:
            return existing
        return _create_project(
            reports_dir, child_identity, load_fn, save_fn, parent_uuid=parent_uuid,
        )

    # --- unscoped resolution ---
    resolved = ProjectIdentity(
        identity.project_name, resolved_path, identity.discipline, identity.location,
    )
    existing = _find_existing_project(reports_dir, resolved, load_fn, save_fn)
    if existing:
        from quodeq.services._fs_projects import find_children
        if find_children(reports_dir, existing):
            dot_identity = ProjectIdentity(
                f"{identity.project_name}/.", resolved_path,
                identity.discipline, identity.location, scope_path=".",
            )
            dot_existing = _find_existing_project(reports_dir, dot_identity, load_fn, save_fn)
            if dot_existing:
                return dot_existing
            return _create_project(
                reports_dir, dot_identity, load_fn, save_fn, parent_uuid=existing,
            )
        return existing
    return _create_project(reports_dir, resolved, load_fn, save_fn)
