"""Filesystem path resolution and containment utilities."""

from __future__ import annotations

from pathlib import Path


def resolve_path(path: str) -> Path:
    """Expand user home and resolve a path string to an absolute Path."""
    return Path(path).expanduser().resolve()


def is_subpath(parent: str, child: str) -> bool:
    """Return True if child is equal to or nested inside parent."""
    p = resolve_path(parent)
    c = resolve_path(child)
    return c == p or p in c.parents


def not_a_directory_reason(path: Path) -> str:
    """Say why *path*, which is not a directory, cannot be used as one.

    A path at a file is a different user mistake from a missing path, so the
    message names which one it is.
    """
    return "points at a file, not a directory" if path.exists() else "does not exist"
