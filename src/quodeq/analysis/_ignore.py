"""Repo-local path exclusions via a .quodeqignore file at the scan root.

Each non-blank, non-comment line is a glob pattern matched against POSIX-style
paths relative to the scan root. A pattern matches the path itself or anything
under it, so ``benchmarks/corpus`` (with or without a trailing slash) excludes
the whole directory. ``*`` crosses directory separators, so ``*.min.js``
excludes matching files at any depth.
"""
from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path
from typing import Sequence

IGNORE_FILENAME = ".quodeqignore"


def load_ignore_patterns(src: Path) -> list[str]:
    """Read patterns from ``src/.quodeqignore``; missing file means no exclusions."""
    ignore_file = src / IGNORE_FILENAME
    try:
        raw = ignore_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    patterns: list[str] = []
    for line in raw.splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if entry.startswith("./"):
            entry = entry[2:]
        entry = entry.rstrip("/")
        if entry:
            patterns.append(entry)
    return patterns


def is_ignored(rel_path: str, patterns: Sequence[str]) -> bool:
    """Return True when *rel_path* (POSIX, relative to the scan root) is excluded."""
    return any(
        fnmatchcase(rel_path, pat) or fnmatchcase(rel_path, pat + "/*")
        for pat in patterns
    )
