"""Standards loaders — read ISO 25010, ASVS, and CISQ standards from JSON files.

Direct file I/O is intentional: these loaders are the canonical path from
on-disk standard definitions into the domain model.
"""
from __future__ import annotations
from pathlib import Path

from quodeq.shared.utils import read_json
from quodeq.shared.validation import validate_path_segment


def _resolve_standards_dir(standards_dir: Path | None = None, *, paths_fn=None) -> Path:
    """Return *standards_dir* or fall back to *paths_fn()*.

    *paths_fn* is an injectable factory that must be supplied by outer layers
    (e.g. ``config.paths.default_paths``).  The core layer does not resolve
    infrastructure paths itself.
    """
    if standards_dir is not None:
        return standards_dir
    if paths_fn is None:
        raise ValueError(
            "standards_dir or paths_fn must be provided; "
            "the core layer cannot resolve infrastructure paths"
        )
    return paths_fn().standards_dir


def _load_json(path: Path, label: str) -> dict:
    """Read and parse a JSON file, raising :class:`FileNotFoundError` on failure.

    *label* is used in the error message to describe what could not be loaded.
    """
    try:
        return read_json(path)
    except (FileNotFoundError, ValueError, UnicodeDecodeError) as exc:
        raise FileNotFoundError(f"Cannot load {label}") from exc


def load_dimension(dimension_id: str, standards_dir: Path | None = None, *, paths_fn=None) -> dict:
    """Load an ISO 25010 dimension definition by its identifier."""
    validate_path_segment(dimension_id)
    resolved = _resolve_standards_dir(standards_dir, paths_fn=paths_fn)
    path = resolved / "iso25010" / f"{dimension_id}.json"
    return _load_json(path, f"dimension '{dimension_id}'")


def load_asvs_l1(standards_dir: Path | None = None, *, paths_fn=None) -> dict:
    """Load OWASP ASVS Level 1 requirements."""
    resolved = _resolve_standards_dir(standards_dir, paths_fn=paths_fn)
    path = resolved / "asvs" / "level1.json"
    return _load_json(path, "ASVS L1 standards")


def load_cisq(characteristic: str, standards_dir: Path | None = None, *, paths_fn=None) -> dict:
    """Load a CISQ quality characteristic definition by name."""
    validate_path_segment(characteristic)
    resolved = _resolve_standards_dir(standards_dir, paths_fn=paths_fn)
    path = resolved / "cisq" / f"{characteristic}.json"
    return _load_json(path, f"CISQ '{characteristic}'")
