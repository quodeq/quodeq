"""Read one hand-editable, advisory JSON config file.

Several project-local config files share one shape: a declared trust
profile, standards overrides, suppression rules, ... Absence means "no
data", and any read/parse failure must degrade rather than propagate --
not just the well-behaved ``OSError``/``ValueError`` (which also covers
invalid JSON and non-UTF-8 bytes, both ``ValueError`` subclasses), but also
``RecursionError``: JSON nested deep enough overflows the C decoder's call
stack, and ``RecursionError`` is a ``RuntimeError`` that would otherwise
escape.

This factors out only the read-or-degrade step. Callers keep their own
shape validation (is it a dict? does it have the right keys?) and their own
log message, since those are specific to what they're loading.
"""
from __future__ import annotations

import json
from pathlib import Path


def read_advisory_json(path: Path) -> tuple[object | None, Exception | None]:
    """Return ``(data, None)``, ``(None, None)`` if *path* is absent, or
    ``(None, error)`` if it exists but is unreadable or malformed.

    *error* is the ``OSError``/``ValueError``/``RecursionError`` that made
    the file unreadable or malformed, so the caller can log its own
    context-specific message before falling back to its own default.
    Anything else (a real bug) is not caught here and propagates.
    """
    if not path.is_file():
        return None, None
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, ValueError, RecursionError) as exc:
        return None, exc
