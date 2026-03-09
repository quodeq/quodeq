from __future__ import annotations
import json
from pathlib import Path


def _standards_dir() -> Path:
    from quodeq.config.paths import default_paths
    return default_paths().standards_dir


def load_dimension(dimension_id: str) -> dict:
    path = _standards_dir() / "iso25010" / f"{dimension_id}.json"
    return json.loads(path.read_text())


def load_asvs_l1() -> dict:
    return json.loads((_standards_dir() / "asvs" / "level1.json").read_text())


def load_cisq(characteristic: str) -> dict:
    path = _standards_dir() / "cisq" / f"{characteristic}.json"
    return json.loads(path.read_text())
