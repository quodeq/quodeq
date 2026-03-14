"""Persistent UUID-based project identity resolution for the reports directory."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_INDEX_FILE = "project_index.json"


class ProjectRepository(Protocol):
    """Abstraction over the storage layer used to persist project identities.

    Implement this protocol to swap the default filesystem backend for a
    different storage technology (database, cloud object store, etc.) without
    changing any callers of ``resolve_project_uuid``.
    """

    def load_index(self, reports_dir: Path) -> dict[str, str]:
        """Load the name→uuid mapping. Return empty dict on missing/corrupt data."""
        ...

    def save_index(self, reports_dir: Path, index: dict[str, str]) -> None:
        """Persist the name→uuid mapping."""
        ...


@dataclass(frozen=True)
class ProjectIdentity:
    """Identifies a project by name, resolved repo path, and metadata."""
    project_name: str
    repo_path: str
    discipline: str | None = None
    location: str = "local"


def _index_key(identity: ProjectIdentity) -> str:
    """Return a stable string key for the (name, path) pair."""
    return f"{identity.project_name}\x00{identity.repo_path}"


def _load_index(reports_dir: Path) -> dict[str, str]:
    """Load the project index file, returning an empty dict on missing/corrupt file."""
    try:
        return json.loads((reports_dir / _INDEX_FILE).read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _save_index(reports_dir: Path, index: dict[str, str]) -> None:
    """Write the project index file atomically."""
    index_path = reports_dir / _INDEX_FILE
    try:
        fd, tmp = tempfile.mkstemp(dir=reports_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(index, f, indent=2)
            os.replace(tmp, index_path)
        except BaseException:
            os.unlink(tmp)
            raise
    except OSError as exc:
        logging.getLogger(__name__).warning("Could not save project index: %s", exc)


def _find_existing_project(reports_dir: Path, identity: ProjectIdentity) -> str | None:
    """Look up project by (name, path) in the index; fall back to directory scan for
    projects created before the index existed, updating the index on success."""
    key = _index_key(identity)
    index = _load_index(reports_dir)
    if key in index:
        # Verify the directory still exists (guard against manual deletion)
        if (reports_dir / index[key]).is_dir():
            return index[key]
        # Index is stale — remove the entry and fall through to scan
        del index[key]
        _save_index(reports_dir, index)

    # Legacy scan: find projects created before the index was introduced
    for entry in reports_dir.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        info_file = entry / "repository_info.json"
        if not info_file.exists():
            continue
        try:
            info = json.loads(info_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if info.get("name") == identity.project_name and info.get("path") == identity.repo_path:
            # Back-fill the index so future lookups are O(1)
            index[key] = entry.name
            _save_index(reports_dir, index)
            return entry.name
    return None


def _create_project(reports_dir: Path, identity: ProjectIdentity) -> str:
    """Create a new UUID project directory, write repository_info.json, and index it."""
    project_uuid = str(uuid.uuid4())
    project_dir = reports_dir / project_uuid
    project_dir.mkdir(parents=True, exist_ok=True)
    info = {
        "uuid": project_uuid,
        "name": identity.project_name,
        "discipline": identity.discipline,
        "location": identity.location,
        "path": identity.repo_path,
    }
    try:
        (project_dir / "repository_info.json").write_text(json.dumps(info, indent=2))
    except OSError as exc:
        logging.getLogger(__name__).warning("Could not write repository_info.json: %s", exc)
    index = _load_index(reports_dir)
    index[_index_key(identity)] = project_uuid
    _save_index(reports_dir, index)
    return project_uuid


def resolve_project_uuid(reports_dir: Path, identity: ProjectIdentity) -> str:
    """Find or create a UUID project directory matching identity."""
    resolved_path = identity.repo_path if identity.location == "online" else Path(identity.repo_path).resolve().name
    resolved = ProjectIdentity(identity.project_name, resolved_path, identity.discipline, identity.location)
    if not reports_dir.exists():
        reports_dir.mkdir(parents=True, exist_ok=True)
    existing = _find_existing_project(reports_dir, resolved)
    if existing:
        return existing
    return _create_project(reports_dir, resolved)
