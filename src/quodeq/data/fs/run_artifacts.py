"""Copy/replace mechanics for staging run artifacts (shared-repo publish).

services/shared_publish decides WHAT gets published (the source-of-truth
allowlist, the glob patterns) and used to perform the shutil/os mechanics
inline too; the mechanics live here. Errors propagate: the publish flow
converts OSError into a user-facing PublishError at its own boundary, so
nothing here may swallow one.
"""
from __future__ import annotations

import json
import os
import shutil
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
    """Write *data* as JSON via a same-directory temp file + atomic replace."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)
