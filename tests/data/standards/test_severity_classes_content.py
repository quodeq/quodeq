"""Every requirement of the built-in standards carries the suggested severity its source declares."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.core.standards.severity_classes import is_severity_class

ROOT = Path(__file__).resolve().parents[3] / "src" / "quodeq" / "data" / "standards"
DIMENSIONS = sorted(p.stem for p in (ROOT / "compiled").glob("*.json"))


def _reqs(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    for principle in data.get("principles", data.get("sub_characteristics", [])):
        for req in principle.get("requirements", []):
            yield req


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_compiled_severity_matches_source_and_is_on_the_ladder(dimension):
    compiled = {r["id"]: r.get("severity") for r in _reqs(ROOT / "compiled" / f"{dimension}.json")}
    source_path = ROOT / "iso25010" / f"{dimension}.json"
    if source_path.is_file():
        source = {r["id"]: r.get("severity") for r in _reqs(source_path)}
        assert compiled == source
    for req_id, value in compiled.items():
        assert is_severity_class(value), (dimension, req_id, value)


def test_security_suggests_a_severity_on_every_requirement():
    assert all(r.get("severity") for r in _reqs(ROOT / "compiled" / "security.json"))
