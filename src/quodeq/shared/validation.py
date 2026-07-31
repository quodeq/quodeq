"""Input validation helpers for path and URL safety."""
from __future__ import annotations

from pathlib import Path


from quodeq.core.utils.io import validate_path_segment  # noqa: F401 — moved inward to core


def validate_relative_scope(scope: str) -> None:
    """Raise ValueError unless *scope* is a plain relative subpath.

    Scope paths (``scopePath`` in project/evaluation payloads) may contain
    forward slashes to point at a nested folder, but must not be absolute,
    drive-qualified, backslashed, or contain traversal segments.
    """
    if "\0" in scope or "\\" in scope:
        raise ValueError(f"Invalid scope path: {scope!r}. Use a forward-slash relative path.")
    if scope.startswith("/") or (len(scope) > 1 and scope[1] == ":"):
        raise ValueError(f"Invalid scope path: {scope!r}. Scope must be relative to the repository root.")
    if any(part == ".." for part in scope.split("/")):
        raise ValueError(f"Invalid scope path: {scope!r}. Parent-directory segments are not allowed.")


def validate_resolved_within(path: Path, root: Path) -> None:
    """Raise ValueError if *path* resolves outside *root*."""
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(
            "Path escapes its root directory. "
            "Ensure the path does not contain '..' segments or symlinks that resolve outside the project root."
        )
