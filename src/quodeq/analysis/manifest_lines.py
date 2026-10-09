"""Source line counting for the manifest.

The line count is recorded beside the file count so a later study of the
scoring denominator has history to work from. Nothing in scoring reads it.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from quodeq.analysis.manifest_models import AnalysisTarget

# Files above this size are skipped: a generated or vendored blob would swamp
# the count without saying anything about hand-written source.
MAX_COUNTED_BYTES = 2 * 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024


def count_source_lines(src: Path, relative_files: Iterable[str]) -> int:
    """Newline count over *relative_files* under *src*; unreadable or oversized files add 0."""
    total = 0
    for rel in relative_files:
        path = src / rel
        try:
            if path.stat().st_size > MAX_COUNTED_BYTES:
                continue
            with path.open("rb") as fh:
                total += sum(chunk.count(b"\n") for chunk in iter(lambda: fh.read(_READ_CHUNK_BYTES), b""))
        except OSError:
            continue
    return total


def count_target_lines(src: Path, targets: Iterable[AnalysisTarget]) -> int:
    """Line count over the union of every target's files, each file counted once."""
    unique = {rel for target in targets for rel in target.source_files}
    return count_source_lines(src, sorted(unique))
