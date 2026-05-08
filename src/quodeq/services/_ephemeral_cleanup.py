"""Lifecycle management for ephemeral clones under ~/.quodeq/clones/."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

_logger = logging.getLogger(__name__)


def _log_rmtree_error(func, path, exc):
    """rmtree onexc callback that logs failures instead of swallowing them."""
    _logger.warning("Failed to remove %s: %s", path, exc)


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
    if not target.exists():
        return
    shutil.rmtree(target, onexc=_log_rmtree_error)


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
            shutil.rmtree(entry, onexc=_log_rmtree_error)
