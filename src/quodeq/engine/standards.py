"""Standards loaders — read ISO 25010, ASVS, and CISQ standards from JSON files."""
from __future__ import annotations
import json
from pathlib import Path


def load_dimension(dimension_id: str, standards_dir: Path | None = None) -> dict:
    """Load an ISO 25010 dimension definition by its identifier."""
    if standards_dir is None:
        from quodeq.config.paths import default_paths
        standards_dir = default_paths().standards_dir
    path = standards_dir / "iso25010" / f"{dimension_id}.json"
    return json.loads(path.read_text())


def load_asvs_l1(standards_dir: Path | None = None) -> dict:
    """Load OWASP ASVS Level 1 requirements."""
    if standards_dir is None:
        from quodeq.config.paths import default_paths
        standards_dir = default_paths().standards_dir
    return json.loads((standards_dir / "asvs" / "level1.json").read_text())


def load_cisq(characteristic: str, standards_dir: Path | None = None) -> dict:
    """Load a CISQ quality characteristic definition by name."""
    if standards_dir is None:
        from quodeq.config.paths import default_paths
        standards_dir = default_paths().standards_dir
    path = standards_dir / "cisq" / f"{characteristic}.json"
    return json.loads(path.read_text())
