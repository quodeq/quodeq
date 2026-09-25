"""Copy/replace mechanics for staging run artifacts (shared-repo publish).

services/shared_publish decides WHAT gets published (the source-of-truth
allowlist, the glob patterns); the shutil/os mechanics live here. Errors propagate: the publish flow
converts OSError into a user-facing PublishError at its own boundary, so
nothing here may swallow one.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from quodeq.shared.json_state import dump_json_and_replace


def ensure_dir(path: Path) -> None:
    """Create *path* (and parents) if absent."""
    path.mkdir(parents=True, exist_ok=True)


def copy_file_if_exists(src: Path, dest: Path) -> bool:
    """Copy *src* to *dest* (metadata preserved) when it exists.

    Returns True when a copy happened. The parent of *dest* must exist.
    """
    if not src.exists():
        return False
    shutil.copy2(src, dest)
    return True


def copy_matching_files(src_dir: Path, dest_dir: Path, pattern: str) -> None:
    """Copy the files in *src_dir* matching *pattern* into *dest_dir*.

    Creates *dest_dir* if needed; sorted for a deterministic copy order.
    """
    ensure_dir(dest_dir)
    for src in sorted(src_dir.glob(pattern)):
        shutil.copy2(src, dest_dir / src.name)


def read_json_object(path: Path, *, raise_non_utf8: bool = False) -> dict | None:
    """Parsed JSON object at *path*.

    None when the file is absent, not valid JSON, not a JSON object, or not
    UTF-8 text. ``raise_non_utf8=True`` lets the UnicodeDecodeError of a
    non-UTF-8 file propagate instead, for callers that treat a non-UTF-8
    record as an error rather than a missing one.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        if raise_non_utf8:
            raise
        return None
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def replace_json_file(path: Path, data: dict) -> None:
    """Write *data* as JSON via a same-directory temp file + atomic replace.

    Uses ``tempfile.mkstemp`` (not a fixed ``.tmp`` suffix) so concurrent
    writers to the same *path* never collide on the same temp name.
    """
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    cleanup_tmp: str | None = tmp_path
    try:
        dump_json_and_replace(fd, tmp_path, path, data)
        cleanup_tmp = None  # ownership transferred to final path
    finally:
        if cleanup_tmp is not None:
            with contextlib.suppress(OSError):
                os.unlink(cleanup_tmp)
