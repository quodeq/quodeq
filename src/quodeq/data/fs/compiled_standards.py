"""Reads over the compiled-standards directory.

api/standards_overrides_routes globbed this directory and json-parsed each
file inline; the mechanics live here so the route keeps only its mapping
logic. Unreadable, unparseable and non-object files are skipped rather
than raised: a single hand-edited standard must never 500 a request.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path


def iter_compiled_standards(compiled_dir: Path) -> Iterator[tuple[str, dict]]:
    """Yield ``(file_stem, payload)`` for each readable compiled standard.

    Sorted by path so callers see a stable order. Skips files that fail to
    read/parse and payloads that are not JSON objects (the recurring
    non-dict-JSON crash class).
    """
    if not compiled_dir.is_dir():
        return
    for path in sorted(compiled_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if isinstance(data, dict):
            yield path.stem, data
