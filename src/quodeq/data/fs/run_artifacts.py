"""Copy/replace mechanics for staging run artifacts (shared-repo publish).

services/shared_publish decides WHAT gets published (the source-of-truth
allowlist, the glob patterns) and used to perform the shutil/os mechanics
inline too; the mechanics live here. Errors propagate: the publish flow
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


def replace_json_file(path: Path, data: dict) -> None:
    """Write *data* as JSON via a same-directory temp file + atomic replace.

    Uses ``tempfile.mkstemp`` (not a fixed ``.tmp`` suffix) so concurrent
    writers to the same *path* never collide on the same temp name.
    """
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    cleanup_tmp: str | None = tmp_path
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data))
        os.replace(tmp_path, str(path))
        cleanup_tmp = None  # ownership transferred to final path
    finally:
        if cleanup_tmp is not None:
            with contextlib.suppress(OSError):
                os.unlink(cleanup_tmp)
