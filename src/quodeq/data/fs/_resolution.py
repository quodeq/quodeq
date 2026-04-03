"""Core project resolution: find existing or create new project directories."""
from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from pathlib import Path

from quodeq.data.fs._index_io import _MAX_LEGACY_SCAN
from quodeq.data.fs._models import ProjectIdentity


def _index_key(identity: ProjectIdentity) -> str:
    """Return a stable string key for the (name, path) pair."""
    return f"{identity.project_name}\x00{identity.repo_path}"


def _find_existing_project(
    reports_dir: Path,
    identity: ProjectIdentity,
    load_fn: Callable[[Path], dict[str, str]],
    save_fn: Callable[[Path, dict[str, str]], None],
) -> str | None:
    """Look up project by (name, path) in the index; fall back to directory scan for
    projects created before the index existed, updating the index on success."""
    key = _index_key(identity)
    index = load_fn(reports_dir)
    if key in index:
        if (reports_dir / index[key]).is_dir():
            return index[key]
        del index[key]
        save_fn(reports_dir, index)

    scanned = 0
    for entry in reports_dir.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        scanned += 1
        if scanned > _MAX_LEGACY_SCAN:
            break
        info_file = entry / "repository_info.json"
        if not info_file.exists():
            continue
        try:
            info = json.loads(info_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if info.get("name") == identity.project_name and info.get("path") == identity.repo_path:
            index[key] = entry.name
            save_fn(reports_dir, index)
            return entry.name
    return None


def _create_project(
    reports_dir: Path,
    identity: ProjectIdentity,
    load_fn: Callable[[Path], dict[str, str]],
    save_fn: Callable[[Path, dict[str, str]], None],
) -> str:
    """Create a new UUID project directory, write repository_info.json, and index it."""
    if identity.location == "online" and not identity.repo_path.startswith(("https://", "git@")):
        logging.getLogger(__name__).warning(
            "Online project '%s' has a non-URL path '%s'; expected a remote URL.",
            identity.project_name,
            identity.repo_path,
        )
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
    index = load_fn(reports_dir)
    index[_index_key(identity)] = project_uuid
    save_fn(reports_dir, index)
    return project_uuid
