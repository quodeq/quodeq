from __future__ import annotations

import json
import uuid
from pathlib import Path


def resolve_project_uuid(reports_dir: Path, project_name: str, repo_path: str, discipline: str | None, location: str = "local") -> str:
    """Find or create a UUID project directory matching project_name + repo_path."""
    resolved = repo_path if location == "online" else str(Path(repo_path).resolve())
    if not reports_dir.exists():
        reports_dir.mkdir(parents=True, exist_ok=True)
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
        if info.get("name") == project_name and info.get("path") == resolved:
            return entry.name
    # No match — create new project directory
    project_uuid = str(uuid.uuid4())
    project_dir = reports_dir / project_uuid
    project_dir.mkdir(parents=True, exist_ok=True)
    info = {
        "uuid": project_uuid,
        "name": project_name,
        "discipline": discipline,
        "location": location,
        "path": resolved,
    }
    (project_dir / "repository_info.json").write_text(json.dumps(info, indent=2))
    return project_uuid
