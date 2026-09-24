"""Raw JSON read mechanics for the repo-identity index (``.repo_index.json``).

services/_repo_index.py owns what the index MEANS (self-heal, the
index-then-walk lookup, key matching) and the write side: ``save_repo_index``
owns its temp-file path across a write-then-cleanup-on-failure sequence, with
two separate log lines (the write failure, and -- if it too fails -- the
temp-file cleanup failure), so that mechanic stays there rather than behind a
raise-only ``write_*`` seam here (see its docstring).
"""
from __future__ import annotations

import json
from pathlib import Path


def read_repo_index(path: Path) -> dict[str, str]:
    """Parsed index JSON at *path*, or {} when absent, corrupt, or not an object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
