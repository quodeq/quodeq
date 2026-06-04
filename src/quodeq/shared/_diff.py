"""Diff display utility."""
from __future__ import annotations

import difflib
from pathlib import Path


def show_diff(path: Path, new_content: str) -> None:
    """Print a unified diff between *path*'s current content and *new_content*."""
    old_lines = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.exists() else []
    new_lines = new_content.splitlines(keepends=True)
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=str(path), tofile="<new>"))
    if diff:
        print("".join(diff))
    else:
        print(f"[no changes] {path}")
