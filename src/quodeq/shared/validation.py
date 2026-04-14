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
