"""Persistent UUID-based project identity resolution for the reports directory."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectIdentity:
    """Identifies a project by name, resolved repo path, and metadata."""
    project_name: str
    repo_path: str
    discipline: str | None = None
    location: str = "local"


def _find_existing_project(reports_dir: Path, identity: ProjectIdentity) -> str | None:
    """Search reports_dir for a project directory matching *identity*."""
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
            return entry.name
    return None


def _create_project(reports_dir: Path, identity: ProjectIdentity) -> str:
    """Create a new UUID project directory and write repository_info.json."""
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
    (project_dir / "repository_info.json").write_text(json.dumps(info, indent=2))
    return project_uuid


def resolve_project_uuid(reports_dir: Path, project_name: str, repo_path: str, discipline: str | None, location: str = "local") -> str:
    """Find or create a UUID project directory matching project_name + repo_path."""
    resolved = repo_path if location == "online" else str(Path(repo_path).resolve())
    identity = ProjectIdentity(project_name, resolved, discipline, location)
    if not reports_dir.exists():
        reports_dir.mkdir(parents=True, exist_ok=True)
    existing = _find_existing_project(reports_dir, identity)
    if existing:
        return existing
    return _create_project(reports_dir, identity)
