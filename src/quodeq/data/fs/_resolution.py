"""Core project resolution: find existing or create new project directories."""
from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from quodeq.data.fs._index_io import _MAX_LEGACY_SCAN
from quodeq.data.fs._models import ProjectIdentity

_REPO_INFO_FILENAME = "repository_info.json"
_LOCATION_ONLINE = "online"
_URL_PREFIXES = ("https://", "git@")


def _index_key(identity: ProjectIdentity) -> str:
    """Return a stable string key for the identity.

    When a git remote URL is present, use it as the primary key component so
    that two clones of the same repo in different local paths resolve to the
    same key. Otherwise fall back to the absolute local path (legacy behavior).
    """
    if identity.remote_url:
        base = f"{identity.project_name}\x00remote:{identity.remote_url}"
    else:
        base = f"{identity.project_name}\x00{identity.repo_path}"
    if identity.scope_path:
        return f"{base}\x00{identity.scope_path}"
    return base


def _find_existing_project(
    reports_dir: Path,
    identity: ProjectIdentity,
    load_fn: Callable[[Path], dict[str, str]],
    save_fn: Callable[[Path, dict[str, str]], None],
) -> str | None:
    """Look up project by identity in the index; fall back to directory scan for
    projects created before the index existed, updating the index on success."""
    key = _index_key(identity)
    index = load_fn(reports_dir)
    if key in index:
        if (reports_dir / index[key]).is_dir():
            return index[key]
        del index[key]
        save_fn(reports_dir, index)

    # Legacy path-based key migration: when a remote_url is set, also try the
    # path-based key that would have been used before remote-URL identity.
    if identity.remote_url:
        legacy_identity = replace(identity, remote_url=None)
        legacy_key = _index_key(legacy_identity)
        if legacy_key in index and (reports_dir / index[legacy_key]).is_dir():
            uuid_value = index[legacy_key]
            index[key] = uuid_value
            save_fn(reports_dir, index)
            return uuid_value

    scanned = 0
    for entry in reports_dir.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        scanned += 1
        if scanned > _MAX_LEGACY_SCAN:
            break
        info_file = entry / _REPO_INFO_FILENAME
        if not info_file.exists():
            continue
        try:
            info = json.loads(info_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if info.get("name") != identity.project_name:
            continue
        # Prefer remote_url match when both sides have one
        if identity.remote_url and info.get("remote_url") == identity.remote_url:
            index[key] = entry.name
            save_fn(reports_dir, index)
            return entry.name
        if info.get("path") == identity.repo_path:
            index[key] = entry.name
            save_fn(reports_dir, index)
            return entry.name
    return None


def _create_project(
    reports_dir: Path,
    identity: ProjectIdentity,
    load_fn: Callable[[Path], dict[str, str]],
    save_fn: Callable[[Path, dict[str, str]], None],
    *,
    parent_uuid: str | None = None,
) -> str:
    """Create a new UUID project directory, write repository_info.json, and index it."""
    if identity.location == _LOCATION_ONLINE and not identity.repo_path.startswith(_URL_PREFIXES):
        logging.getLogger(__name__).warning(
            "Online project '%s' has a non-URL path '%s'; expected a remote URL.",
            identity.project_name,
            identity.repo_path,
        )
    project_uuid = str(uuid.uuid4())
    project_dir = reports_dir / project_uuid
    project_dir.mkdir(parents=True, exist_ok=True)
    info: dict[str, object] = {
        "uuid": project_uuid,
        "name": identity.project_name,
        "discipline": identity.discipline,
        "location": identity.location,
        "path": identity.repo_path,
    }
    if identity.scope_path:
        info["scopePath"] = identity.scope_path
    if identity.remote_url:
        info["remote_url"] = identity.remote_url
    if parent_uuid:
        info["parent"] = parent_uuid
    try:
        (project_dir / _REPO_INFO_FILENAME).write_text(json.dumps(info, indent=2), encoding="utf-8")
    except OSError as exc:
        logging.getLogger(__name__).warning("Could not write repository_info.json: %s", exc)
    index = load_fn(reports_dir)
    index[_index_key(identity)] = project_uuid
    save_fn(reports_dir, index)
    return project_uuid
