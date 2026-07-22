"""Lifecycle management for ephemeral clones under ~/.quodeq/clones/."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.services.shared_repo import remove_clone_dir

_logger = logging.getLogger(__name__)


def delete_ephemeral_clone(clones_root: Path, project_uuid: str) -> None:
    """Remove the ephemeral clone directory for *project_uuid*.

    Path-traversal safe: only removes directories that resolve to a direct
    child of *clones_root*. Missing directories are a no-op.
    """
    clones_root = Path(clones_root).resolve()
    target = (clones_root / project_uuid).resolve()
    try:
        target.relative_to(clones_root)
    except ValueError:
        _logger.warning("Refusing to delete %s (outside clones root)", target)
        return
    if target == clones_root:
        return
    remove_clone_dir(target)


def maybe_cleanup_after_job(
    *,
    reports_root: Path,
    project_uuid: str,
    clones_root: Path,
) -> None:
    """Delete the ephemeral clone for *project_uuid* if its info file says so.

    Reads ``<reports_root>/<project_uuid>/repository_info.json`` and only
    removes the clone when ``info["ephemeral"]`` is truthy. Missing or
    unreadable info files (including corrupt JSON) are no-ops so the
    JobManager on-complete callback never raises on incomplete state.
    """
    info_path = Path(reports_root) / project_uuid / "repository_info.json"
    try:
        raw = info_path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return
    try:
        info = json.loads(raw)
    except ValueError:
        return
    if not isinstance(info, dict) or not info.get("ephemeral"):
        return
    delete_ephemeral_clone(Path(clones_root), project_uuid)


def sweep_orphaned_clones(clones_root: Path, reports_root: Path) -> None:
    """Remove clone dirs whose UUIDs are not registered project directories.

    Called once at app startup to clean up after crashes or process kills
    that prevented post-evaluation cleanup from running.
    """
    clones_root = Path(clones_root)
    reports_root = Path(reports_root)
    if not clones_root.is_dir():
        return
    if reports_root.is_dir():
        registered = {p.name for p in reports_root.iterdir() if p.is_dir()}
    else:
        registered = set()
    for entry in clones_root.iterdir():
        if entry.is_dir() and entry.name not in registered:
            remove_clone_dir(entry)
