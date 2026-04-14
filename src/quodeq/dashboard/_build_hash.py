"""Hash-based rebuild detection for UI source files."""
from __future__ import annotations

import hashlib
from pathlib import Path

from quodeq import __version__
from quodeq.shared.logging import log_debug

_HASH_FILE = ".build_hash"
_READ_CHUNK_SIZE = 1 << 16

# Files and directories to sync from package source to build workdir
_SYNC_ITEMS = ("src", "public", "package.json", "package-lock.json", ".npmrc", "vite.config.js", "index.html")


def compute_source_hash(source_dir: Path) -> str:
    """Compute a SHA-256 hash over all tracked source files and the package version."""
    h = hashlib.sha256()
    h.update(__version__.encode())
    files: list[Path] = []
    for item_name in _SYNC_ITEMS:
        item = source_dir / item_name
        if item.is_file():
            files.append(item)
        elif item.is_dir():
            files.extend(sorted(f for f in item.rglob("*") if f.is_file()))
    for f in sorted(files):
        rel = f.relative_to(source_dir)
        try:
            h.update(str(rel).encode())
            with open(f, "rb") as fh:
                while chunk := fh.read(_READ_CHUNK_SIZE):
                    h.update(chunk)
        except OSError as exc:
            log_debug(f"Skipping {f.name} in source hash: {exc}")
            continue
    return h.hexdigest()


def needs_rebuild(source_dir: Path, static_dir: Path, reinstall: bool) -> bool:
    """Return True if the UI needs to be rebuilt."""
    if reinstall:
        return True
    if not (static_dir / "index.html").exists():
        return True
    hash_file = static_dir / _HASH_FILE
    if not hash_file.exists():
        return True
    stored_hash = hash_file.read_text().strip()
    current_hash = compute_source_hash(source_dir)
    return stored_hash != current_hash
