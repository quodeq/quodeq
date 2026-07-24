"""Input validation helpers for path and URL safety."""
from __future__ import annotations

from pathlib import Path


def validate_path_segment(*segments: str) -> None:
    """Raise ValueError if any segment contains path traversal or separator characters."""
    for seg in segments:
        if ".." in seg or "/" in seg or "\\" in seg or "\0" in seg:
            raise ValueError(
                f"Invalid path segment: {seg!r}. "
                f"Use only alphanumeric characters, hyphens, underscores, and dots."
            )


def validate_resolved_within(path: Path, root: Path) -> None:
    """Raise ValueError if *path* resolves outside *root*."""
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(
            "Path escapes its root directory. "
            "Ensure the path does not contain '..' segments or symlinks that resolve outside the project root."
        )


def jailed_run_dir(reports_root: Path, project: str, run_id: str) -> Path:
    """Return reports_root/project/run_id, guaranteed within reports_root.

    Raises ValueError on traversal/separators or if the resolved path escapes
    reports_root. The inline resolve()+is_relative_to guard is the recognized
    path-injection barrier (same shape as api._project_dir); reports_root is
    trusted app config, so the returned path is safe to use for filesystem access.
    """
    validate_path_segment(project, run_id)
    base = Path(reports_root).resolve()
    resolved = (base / project / run_id).resolve()
    if not resolved.is_relative_to(base):
        raise ValueError("Run directory escapes the evaluations root.")
    return resolved
