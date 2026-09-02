"""Small metadata-reading primitives for the filesystem action provider.

Split out of _fs_metadata.py (Task 13): the leaf reads (scan summary, path
existence, project metadata extraction, repository info) that
``_compute_summary`` and the project-entry builders assemble into a project
card.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.services._wiring import read_repository_info, read_scan_json


def _read_scan_summary(reports_root: Path, entry_name: str) -> dict[str, Any]:
    """Read scan.json and return coverage fields, or empty dict if not available."""
    data = read_scan_json(reports_root / entry_name)
    if data is None:
        return {}
    return {"scanDate": data.get("scanned_at"), "totalFiles": data.get("total_files")}


def _check_path_exists(path: str | None, location: str | None) -> bool | None:
    """Return whether a local path exists, or None if not applicable."""
    if location == "local" and path:
        return Path(path).exists()
    return None


def _extract_project_metadata(info: dict[str, Any], entry_name: str) -> dict[str, Any]:
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


def _read_repo_info(reports_root: Path, entry_name: str) -> dict[str, Any]:
    """Read repository_info.json for a project, returning an empty dict on failure."""
    return read_repository_info(reports_root / entry_name) or {}


def _local_repo_root(reports_root: Path, entry_name: str) -> Path | None:
    """The analyzed repo's local working copy, or None when there isn't one.

    Same gate as the API's ``repo_attach_info``: a recorded path that is not
    an online URL and still exists as a directory. Online projects and moved
    working copies resolve to None, which downstream visibility lookups treat
    as "use the default selection".
    """
    info = _read_repo_info(reports_root, entry_name)
    path = info.get("path")
    if not path or not isinstance(path, str):
        return None
    if str(info.get("location", "")).lower() == "online" or "://" in path:
        return None
    root = Path(path)
    return root if root.is_dir() else None
