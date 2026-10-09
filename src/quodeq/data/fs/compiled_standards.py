"""Reads over the compiled-standards directory.

api/standards_overrides_routes globbed this directory and json-parsed each
file inline; the mechanics live here so the route keeps only its mapping
logic. Unreadable, unparseable and non-object files are skipped rather
than raised: a single hand-edited standard must never 500 a request.

"Unparseable" means every failure mode, not the well-behaved
``OSError``/``ValueError``/``UnicodeDecodeError`` trio: deeply nested JSON
overflows the C decoder's call stack and raises ``RecursionError``, which is a
``RuntimeError`` and would otherwise escape and 500 the very request this
module exists to protect.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

from quodeq.core.standards.severity_classes import extract_severity_classes

_logger = logging.getLogger(__name__)


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
        except (OSError, ValueError, RecursionError) as exc:
            _logger.warning("Skipping unreadable compiled standard %s: %s", path, exc)
            continue
        if isinstance(data, dict):
            yield path.stem, data


def read_severity_classes(
    compiled_dir: str | Path | None, evaluators_dir: str | Path | None = None,
) -> dict[str, str]:
    """``{req_id: class}`` over every standard on disk; custom evaluators win on a shared id.

    Unreadable or non-object files are skipped with a warning: one hand-edited
    standard must never take the grade down with it.
    """
    classes: dict[str, str] = {}
    for directory in (compiled_dir, evaluators_dir):
        if not directory:
            continue
        for _stem, data in iter_compiled_standards(Path(directory)):
            classes.update(extract_severity_classes(data))
    return classes
