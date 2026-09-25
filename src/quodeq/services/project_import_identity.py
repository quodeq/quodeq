"""Project-identity helpers for import: collision detection and index updates.

The import route uses these to find an existing project with the same
identity, rewrite the imported ``repository_info.json`` with its new UUID and
register it in ``project_index.json``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.services.project_index import (
    ProjectIdentity,
    ProjectRepository,
    index_key,
    load_index,
    save_index,
)
from quodeq.core.types.project_source import ProjectLocation
from quodeq.services._repo_index import RepoIdentity
from quodeq.services.wiring import read_repository_info, write_repository_info

REPO_INFO_FILENAME = "repository_info.json"


def _optional_str(info: dict[str, Any], key: str) -> str | None:
    value = info.get(key)
    return value if isinstance(value, str) else None


def identity_from_info(info: dict[str, Any]) -> ProjectIdentity:
    """Build a ``ProjectIdentity`` from a parsed ``repository_info.json`` payload."""
    return ProjectIdentity(
        project_name=str(info.get("name") or ""),
        repo_path=str(info.get("path") or ""),
        discipline=_optional_str(info, "discipline"),
        location=str(info.get("location") or ProjectLocation.LOCAL),
        scope_path=_optional_str(info, "scopePath"),
        remote_url=_optional_str(info, "remote_url"),
    )


def _index_collision(reports_root: Path, identity: ProjectIdentity, ignore_uuid: str) -> str | None:
    """O(1) index lookup for a colliding project (mirrors ``update_index``'s
    use of the same index)."""
    index = load_index(reports_root)
    candidate = index.get(index_key(identity))
    if candidate is not None and candidate != ignore_uuid:
        return candidate
    return None


def _walk_for_collision(
    reports_root: Path, identity: ProjectIdentity, ignore_uuid: str, *, log: LogSink = NULL_LOG,
) -> str | None:
    """Directory-walk fallback: reads each project's repository_info.json
    directly, mirroring ``_scan_legacy_projects``'s self-healing pattern."""
    if not reports_root.is_dir():
        return None
    wanted = RepoIdentity(identity.project_name, identity.repo_path, identity.scope_path)
    for child in reports_root.iterdir():
        if not child.is_dir() or child.name == ignore_uuid:
            continue
        data = read_repository_info(child)
        if data is None or not wanted.matches_record(data):
            continue
        update_index(reports_root, identity, child.name, log=log)
        return child.name
    return None


def find_identity_collision(
    reports_root: Path, identity: ProjectIdentity, *, ignore_uuid: str, log: LogSink = NULL_LOG,
) -> str | None:
    """Return the UUID of any other project matching this identity.

    Fast path: O(1) index lookup instead of a directory walk + repository_info.json
    parse per existing project.

    Fallback: the index is not guaranteed to have an entry for every project on
    disk (legacy projects created before the index existed, or an imported
    project whose best-effort index write failed). On a miss we fall back to
    walking ``reports_root`` and reading each ``repository_info.json`` directly;
    a fallback hit is written back into the index so subsequent lookups for
    that project take the fast path.
    """
    collision = _index_collision(reports_root, identity, ignore_uuid)
    if collision is not None:
        return collision
    return _walk_for_collision(reports_root, identity, ignore_uuid, log=log)


def rewrite_repository_info(project_dir: Path, new_uuid: str, *, log: LogSink = NULL_LOG) -> None:
    """Update the imported project's repository_info.json with its new UUID."""
    data = read_repository_info(project_dir)
    if data is None:
        return
    data["uuid"] = new_uuid
    if not write_repository_info(project_dir, data):
        log.warning(f"import: could not rewrite repository_info.json for {project_dir}")


def update_index(
    reports_root: Path,
    identity: ProjectIdentity,
    project_uuid: str,
    repository: ProjectRepository | None = None,
    *,
    log: LogSink = NULL_LOG,
) -> None:
    """Best-effort: register the imported project in project_index.json.

    When *repository* is provided its ``load_index``/``save_index`` methods
    are used instead of the default filesystem helpers, keeping the storage
    layer injectable for testing or alternative backends.
    """
    load_fn = repository.load_index if repository is not None else load_index
    save_fn = repository.save_index if repository is not None else save_index
    try:
        index = load_fn(reports_root)
        index[index_key(identity)] = project_uuid
        save_fn(reports_root, index)
    except OSError as exc:
        log.warning(f"import: could not update project_index.json: {exc}")
