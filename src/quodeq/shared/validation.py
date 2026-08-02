"""Input validation helpers for path and URL safety."""
from __future__ import annotations

from pathlib import Path


from quodeq.core.utils.io import (  # noqa: F401 — moved inward to core
    contained_path,
    validate_path_segment,
)


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


def validate_resolved_within(path: Path, root: Path) -> Path:
    """Return *path* contained within *root*, raising ValueError if it escapes.

    Thin ``Path``-typed wrapper over :func:`contained_path`. Use the returned
    value, not the argument you passed in: the point of the check is that the
    contained path is what flows onward.
    """
    return Path(contained_path(path, root))
