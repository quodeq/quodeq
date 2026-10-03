"""Small metadata-reading primitives for the filesystem action provider.

Split out of _fs_metadata.py: the leaf reads (path existence, project
metadata extraction, repository info) that ``_compute_summary`` and the
project-entry builders assemble into a project card.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.core.types.project_source import ProjectLocation
from quodeq.services.wiring import read_repository_info


def check_path_exists(path: str | None, location: str | None) -> bool | None:
    """Return whether a local path exists, or None if not applicable."""
    if location == ProjectLocation.LOCAL and path:
        return Path(path).exists()
    return None


def extract_project_metadata(info: dict[str, Any], entry_name: str) -> dict[str, Any]:
    """Extract and normalize optional metadata fields from repository info."""
    return {
        "name": info.get("name") or entry_name,
        "parent": info.get("parent") or None,
        "displayName": info.get("displayName") or None,
        "discipline": info.get("discipline") or None,
        "path": info.get("path") or None,
        "location": info.get("location") or None,
        "scopePath": info.get("scopePath") or None,
    }


def read_repo_info(reports_root: Path, entry_name: str) -> dict[str, Any]:
    """Read repository_info.json for a project, returning an empty dict on failure."""
    return read_repository_info(reports_root / entry_name) or {}


def repo_attach_reason(info: dict[str, Any]) -> tuple[str | None, str | None]:
    """``(path, reason)`` for a project's repository_info.json payload *info*.

    Reasons: ok, no_recorded_path, online_project, path_missing. Shared by
    the API's ``repo_attach_info`` (which handles the project_id-level
    reasons -- no_project, unknown_project -- before calling this) and
    ``local_repo_root`` below.
    """
    path = info.get("path")
    if not path or not isinstance(path, str):
        return None, "no_recorded_path"
    if str(info.get("location", "")).lower() == ProjectLocation.ONLINE or "://" in path:
        return None, "online_project"
    if not Path(path).is_dir():
        return None, "path_missing"
    return path, "ok"


def local_repo_root(reports_root: Path, entry_name: str) -> Path | None:
    """The analyzed repo's local working copy, or None when there isn't one.

    Same gate as the API's ``repo_attach_info``: a recorded path that is not
    an online URL and still exists as a directory. Online projects and moved
    working copies resolve to None, which downstream visibility lookups treat
    as "use the default selection".
    """
    path, _ = repo_attach_reason(read_repo_info(reports_root, entry_name))
    return Path(path) if path else None
