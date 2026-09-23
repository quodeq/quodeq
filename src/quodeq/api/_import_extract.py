"""Safe extraction of validated zip members onto disk.

Split out of import_project.py. ``safe_extract`` runs after
``_import_validation.validate_archive`` has already rejected traversal,
symlinks, and oversize members; it still double-checks each target path
before writing, as a second line of defense. ``swap_into_place`` moves a
staged project over an existing one without ever leaving neither on disk.
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from ._import_validation import bad_request


def safe_extract(zf: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo], dest: Path) -> None:
    """Extract validated members into *dest*, double-checking each target path."""
    dest_resolved = dest.resolve()
    for arcname, info in members.items():
        target = (dest / arcname).resolve()
        if target != dest_resolved and not target.is_relative_to(dest_resolved):
            raise bad_request(f"Archive member would escape target dir: {arcname!r}", "PATH_ESCAPE")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst, length=64 * 1024)


_REPLACED_BACKUP = ".replaced"


def swap_into_place(staged: Path, final: Path, staging: Path) -> None:
    """Move *final* aside into *staging*, then *staged* into its place.

    The old project is restored if the second move fails, so a failed
    replace never loses it. The backup is dropped with *staging*.
    """
    backup = staging / _REPLACED_BACKUP
    final.rename(backup)
    try:
        staged.rename(final)
    except OSError:
        backup.rename(final)
        raise
