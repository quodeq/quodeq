"""Raw JSON read/write mechanics for the repo-identity index (``.repo_index.json``).

services/_repo_index.py owns what the index MEANS (self-heal, the
index-then-walk lookup, key matching) and the outer best-effort save
semantics (``save_repo_index`` logs a warning and swallows a write failure);
the JSON file mechanics -- including the same-dir temp file, the atomic
replace, and a best-effort cleanup of that temp file on failure -- live here.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.shared.json_state import dump_json_and_replace


def read_repo_index(path: Path) -> dict[str, str]:
    """Parsed index JSON at *path*, or {} when absent, corrupt, or not an object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_repo_index(path: Path, data: dict[str, str], *, log: LogSink = NULL_LOG) -> None:
    """Write *data* as the index JSON via a same-dir temp file + atomic replace.

    Raises OSError on a write failure -- the caller (``save_repo_index``)
    decides how to log/swallow it. On that failure this makes a best-effort
    attempt to remove the leftover temp file; if THAT also fails, it is
    logged as a debug message via *log* rather than raised, so the original
    write failure is always what propagates.
    """
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        dump_json_and_replace(fd, tmp_path, path, data, indent=2)
    except OSError:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError as inner_exc:
                log.debug(f"temp repo index file not removed after a failed save: {inner_exc}")
        raise
