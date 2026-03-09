from pathlib import Path


def resolve_path(path: str) -> Path:
    return Path(path).expanduser().resolve()


def is_subpath(parent: str, child: str) -> bool:
    p = resolve_path(parent)
    c = resolve_path(child)
    return c == p or p in c.parents
