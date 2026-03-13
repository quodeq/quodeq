"""Standards loaders — read ISO 25010, ASVS, and CISQ standards from JSON files."""
from __future__ import annotations
import json
from pathlib import Path


def _resolve_standards_dir(standards_dir: Path | None) -> Path:
    """Return *standards_dir* or fall back to the project default."""
    if standards_dir is not None:
        return standards_dir
    from quodeq.config.paths import default_paths
    return default_paths().standards_dir


def load_dimension(dimension_id: str, standards_dir: Path | None = None) -> dict:
    """Load an ISO 25010 dimension definition by its identifier."""
    resolved = _resolve_standards_dir(standards_dir)
    path = resolved / "iso25010" / f"{dimension_id}.json"
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FileNotFoundError(f"Cannot load dimension '{dimension_id}' from {path}: {exc}") from exc


def load_asvs_l1(standards_dir: Path | None = None) -> dict:
    """Load OWASP ASVS Level 1 requirements."""
    resolved = _resolve_standards_dir(standards_dir)
    return json.loads((resolved / "asvs" / "level1.json").read_text())


def load_cisq(characteristic: str, standards_dir: Path | None = None) -> dict:
    """Load a CISQ quality characteristic definition by name."""
    resolved = _resolve_standards_dir(standards_dir)
    path = resolved / "cisq" / f"{characteristic}.json"
    return json.loads(path.read_text())
