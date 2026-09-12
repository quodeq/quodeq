"""Parent/child project relationships read from repository_info.json."""
from __future__ import annotations

from pathlib import Path

from quodeq.core.utils.io import read_json


def find_children(reports_root: Path, parent_id: str) -> list[str]:
    """Return UUIDs of child projects whose parent matches *parent_id*."""
    children: list[str] = []
    for entry in reports_root.iterdir():
        if not entry.is_dir() or entry.name == parent_id:
            continue
        info_path = entry / "repository_info.json"
        if not info_path.exists():
            continue
        try:
            info = read_json(info_path)
            if info.get("parent") == parent_id:
                children.append(entry.name)
        except ValueError:
            continue
    return children
