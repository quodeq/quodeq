from __future__ import annotations
import json
from pathlib import Path

STANDARDS_DIR = Path(__file__).parent.parent.parent.parent.parent / "v2" / "standards"


def load_dimension(dimension_id: str) -> dict:
    path = STANDARDS_DIR / "iso25010" / f"{dimension_id}.json"
    return json.loads(path.read_text())


def load_asvs_l1() -> dict:
    return json.loads((STANDARDS_DIR / "asvs" / "level1.json").read_text())


def load_cisq(characteristic: str) -> dict:
    path = STANDARDS_DIR / "cisq" / f"{characteristic}.json"
    return json.loads(path.read_text())
