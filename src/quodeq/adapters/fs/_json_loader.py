"""Shared JSON-file loading utility for filesystem-backed repositories."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.ports.data_errors import NotFoundError


def list_json_dir(directory: Path, not_found_label: str) -> list[str]:
    """Return sorted stems of all JSON files in *directory*.

    Raises ``NotFoundError`` when *directory* does not exist.

    Example::

        names = list_json_dir(root / "dimensions", "Dimensions directory not found")
    """
    if not directory.exists():
        raise NotFoundError(f"{not_found_label}: {directory}")
    return sorted(path.stem for path in directory.glob("*.json") if path.is_file())


def get_json_file(directory: Path, stem: str, not_found_label: str) -> dict:
    """Load and return a JSON dict for *stem* from *directory*.

    Raises ``NotFoundError`` when the file is missing or contains invalid JSON.

    Example::

        dim = get_json_file(root / "dimensions", "security", "Dimension not found")
    """
    return load_json_file(directory / f"{stem}.json", f"{not_found_label}: {stem}")


def load_json_file(path: Path, label: str) -> dict:
    """Load and return a JSON dict from *path*, raising NotFoundError on failure.

    *label* is used in error messages (e.g. ``"Dimension not found: security"``).
    """
    if not path.exists():
        raise NotFoundError(f"{label}")
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise NotFoundError(
            f"Invalid JSON in {label} — check the file for syntax errors or validate with a JSON linter"
        ) from exc
