"""Safe extraction of validated zip members onto disk.

Split out of import_project.py (Task 9). ``_safe_extract`` runs after
``_import_validation._validate_archive`` has already rejected traversal,
symlinks, and oversize members; it still double-checks each target path
before writing, as a second line of defense.
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from ._import_validation import _bad_request


def _safe_extract(zf: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo], dest: Path) -> None:
    """Extract validated members into *dest*, double-checking each target path."""
    dest_resolved = dest.resolve()
    for arcname, info in members.items():
        target = (dest / arcname).resolve()
        if target != dest_resolved and not target.is_relative_to(dest_resolved):
            raise _bad_request(f"Archive member would escape target dir: {arcname!r}", "PATH_ESCAPE")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst, length=64 * 1024)
