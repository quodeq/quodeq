"""Filesystem path resolution and containment utilities."""

from pathlib import Path


def resolve_path(path: str) -> Path:
    """Expand user home and resolve a path string to an absolute Path."""
    return Path(path).expanduser().resolve()


def is_subpath(parent: str, child: str) -> bool:
    """Return True if child is equal to or nested inside parent."""
    p = resolve_path(parent)
    c = resolve_path(child)
    return c == p or p in c.parents
