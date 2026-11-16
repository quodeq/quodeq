"""Read a project's source files as text, for checkers that scan content."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

_logger = logging.getLogger(__name__)

# Generated bundles and data dumps past this size are not hand-written
# source; scanning them costs time and finds nothing a person typed.
MAX_SCAN_BYTES = 2 * 1024 * 1024


def read_source_texts(root: Path, files: Iterable[Path]) -> list[tuple[str, str]]:
    """``(repo-relative posix path, text)`` for each readable file inside *root*.

    Paths that resolve outside *root* (including through a symlink) are
    skipped, as are binaries, undecodable files and files over
    ``MAX_SCAN_BYTES``.
    """
    base = root.resolve()
    out: list[tuple[str, str]] = []
    for raw in files:
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(base) or not resolved.is_file():
                continue
            if resolved.stat().st_size > MAX_SCAN_BYTES:
                continue
            text = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            _logger.debug("source_texts: skipping unreadable %s", path)
            continue
        out.append((resolved.relative_to(base).as_posix(), text))
    return out
