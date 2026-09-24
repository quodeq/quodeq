"""Working-copy facts derived from a project's stored repo path."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quodeq.core.types.project_source import ProjectLocation


def _derive_last_fetched_at(repo_path: str | None) -> str | None:
    """Return ISO-8601 mtime of .git/FETCH_HEAD (or .git/HEAD as fallback), or None."""
    if not repo_path:
        return None
    p = Path(repo_path)
    fetch_head = p / ".git" / "FETCH_HEAD"
    head = p / ".git" / "HEAD"
    candidate = fetch_head if fetch_head.exists() else head if head.exists() else None
    if candidate is None:
        return None
    try:
        ts = candidate.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _is_evaluable(repo_path: str | None) -> bool:
    """Return True if the working copy directory exists on disk."""
    if not repo_path:
        return False
    return Path(repo_path).is_dir()


def annotate_working_copy(info: dict[str, Any]) -> None:
    """Stamp *info* with the working-copy facts derived from its ``path``."""
    repo_path = info.get("path")
    info["lastFetchedAt"] = _derive_last_fetched_at(repo_path)
    info["evaluable"] = _is_evaluable(repo_path)
    info.setdefault("ephemeral", False)


def online_path_missing(info: dict[str, Any]) -> bool:
    """True for an online project whose stored path is not a remote URL."""
    return (
        info.get("location") == ProjectLocation.ONLINE
        and not (info.get("path", "").startswith(("https://", "git@")))
    )
