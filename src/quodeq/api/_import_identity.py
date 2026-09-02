"""Project-identity helpers for import: collision detection and index updates.

Split out of import_project.py (Task 9).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quodeq.services.project_index import (
    ProjectIdentity,
    ProjectRepository,
    index_key,
    load_index,
    save_index,
)

from ._import_validation import _logger

_REPO_INFO_FILENAME = "repository_info.json"


def _identity_from_info(info: dict[str, Any]) -> ProjectIdentity:
    return ProjectIdentity(
        project_name=str(info.get("name") or ""),
        repo_path=str(info.get("path") or ""),
        discipline=info.get("discipline") if isinstance(info.get("discipline"), str) else None,
        location=str(info.get("location") or "local"),
        scope_path=info.get("scopePath") if isinstance(info.get("scopePath"), str) else None,
        remote_url=info.get("remote_url") if isinstance(info.get("remote_url"), str) else None,
    )


def _find_identity_collision(reports_root: Path, identity: ProjectIdentity, *, ignore_uuid: str) -> str | None:
    """Return the UUID of any other project matching this identity.

    Fast path: O(1) index lookup instead of a directory walk + repository_info.json
    parse per existing project (mirrors ``_update_index``'s use of the same index).

    Fallback: the index is not guaranteed to have an entry for every project on
    disk (legacy projects created before the index existed, or an imported
    project whose best-effort index write failed). On a miss we fall back to
    walking ``reports_root`` and reading each ``repository_info.json`` directly,
    mirroring ``_scan_legacy_projects``'s self-healing pattern: a fallback hit
    is written back into the index so subsequent lookups for that project take
    the fast path.
    """
    index = load_index(reports_root)
    candidate = index.get(index_key(identity))
    if candidate is not None:
        return None if candidate == ignore_uuid else candidate

    if not reports_root.is_dir():
        return None
    for child in reports_root.iterdir():
        if not child.is_dir() or child.name == ignore_uuid:
            continue
        info_file = child / _REPO_INFO_FILENAME
        if not info_file.exists():
            continue
        try:
            data = json.loads(info_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("name") != identity.project_name:
            continue
        if data.get("path") != identity.repo_path:
            continue
        if (data.get("scopePath") or None) != (identity.scope_path or None):
            continue
        try:
            index[index_key(identity)] = child.name
            save_index(reports_root, index)
        except OSError as exc:
            _logger.warning("import: could not update project_index.json: %s", exc)
        return child.name
    return None


def _rewrite_repository_info(project_dir: Path, new_uuid: str) -> None:
    """Update the imported project's repository_info.json with its new UUID."""
    info_path = project_dir / _REPO_INFO_FILENAME
    try:
        data = json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    data["uuid"] = new_uuid
    try:
        info_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        _logger.warning("import: could not rewrite repository_info.json: %s", exc)


def _update_index(
    reports_root: Path,
    identity: ProjectIdentity,
    project_uuid: str,
    repository: ProjectRepository | None = None,
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
        _logger.warning("import: could not update project_index.json: %s", exc)
