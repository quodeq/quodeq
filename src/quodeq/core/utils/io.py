"""Low-level text/JSON read helpers with centralized encoding.

These live in core (stdlib-only, no outward imports) so domain modules like
the evidence parser and standards loader can use them without reaching into
``shared/``. ``shared/_io.py`` re-exports them for the rest of the codebase.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import IO, Any

TEXT_ENCODING = "utf-8"
"""Standard text encoding used across the codebase for file I/O."""


def open_text(path: str | Path, mode: str = "r") -> IO[str]:
    """Open a text file with the standard encoding. Use as a context manager."""
    return open(path, mode, encoding=TEXT_ENCODING)


def read_json(path: Path) -> dict[str, Any]:
    """Read and parse a JSON object file, returning the parsed dict.

    Enforces the ``-> dict`` contract: a valid-JSON-but-non-object payload (a
    top-level list, string, number, or null) raises ``ValueError`` — the same
    failure mode as a read/parse error. This shuts down the recurring crash
    class where a caller does ``read_json(p).get(...)`` and a hand-edited or
    malformed file that is valid JSON but not an object raises an unhandled
    ``AttributeError`` deep in the caller. Callers that load top-level arrays
    must use a plain ``json.loads`` (or ``default_read_json``), not this helper.
    """
    try:
        data = json.loads(path.read_text(encoding=TEXT_ENCODING))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a JSON object in {path}, got {type(data).__name__}"
        )
    return data


def validate_path_segment(*segments: str) -> None:
    """Raise ValueError if any segment contains path traversal or separator characters."""
    for seg in segments:
        if ".." in seg or "/" in seg or "\\" in seg or "\0" in seg:
            raise ValueError(
                f"Invalid path segment: {seg!r}. "
                f"Use only alphanumeric characters, hyphens, underscores, and dots."
            )
