"""Shared JSON-file loading utility for filesystem-backed repositories."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.ports.data_errors import NotFoundError


def load_json_file(path: Path, label: str) -> dict:
    """Load and return a JSON dict from *path*, raising NotFoundError on failure.

    *label* is used in error messages (e.g. ``"Dimension not found: security"``).
    """
    if not path.exists():
        raise NotFoundError(f"{label}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise NotFoundError(f"Invalid JSON in {label}") from exc
