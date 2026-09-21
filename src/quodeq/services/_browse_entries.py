"""The directory scan the browse endpoints share.

``tooling_mixin`` lists subdirectories and source files out of the same
scandir, with the same hidden-name and readability rules. Those rules live
here so the two listings cannot drift, and so ``tooling_mixin`` stays under
the size ratchet's 300-line cap.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from quodeq.data.fs.report_parser import safe_read_dir


def readable_entries(
    target: Path, entries: list[os.DirEntry[str]] | None, *, want_dirs: bool,
) -> Iterator[tuple[os.DirEntry[str], Path]]:
    """Yield ``(entry, path)`` for each readable, non-hidden child of *target*.

    *want_dirs* keeps directories; otherwise files are kept. Dot-named
    entries and entries the process cannot read are skipped. *entries*
    supplies an already-read listing so a caller that needs both kinds does
    not pay for a second scandir.
    """
    for entry in (safe_read_dir(target) if entries is None else entries):
        if entry.name.startswith("."):
            continue
        if not (entry.is_dir() if want_dirs else entry.is_file()):
            continue
        entry_path = target / entry.name
        if not os.access(entry_path, os.R_OK):
            continue
        yield entry, entry_path
