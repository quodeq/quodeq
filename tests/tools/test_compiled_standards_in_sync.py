"""Compiled standards must carry their ISO 25010 source text verbatim."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_STANDARDS = Path(__file__).resolve().parents[2] / "src" / "quodeq" / "data" / "standards"
_DIMENSIONS = ("maintainability", "reliability", "performance", "usability", "flexibility")


def _iso_texts(dimension: str) -> dict[str, str]:
    data = json.loads((_STANDARDS / "iso25010" / f"{dimension}.json").read_text(encoding="utf-8"))
    return {
        req["id"]: req["text"]
        for sub in data.get("sub_characteristics", [])
        for req in sub.get("requirements", [])
    }


def _compiled_texts(dimension: str) -> dict[str, str]:
    data = json.loads((_STANDARDS / "compiled" / f"{dimension}.json").read_text(encoding="utf-8"))
    return {
        req["id"]: req["text"]
        for principle in data["principles"]
        for req in principle.get("requirements", [])
        if req.get("source") == "iso25010"
    }


@pytest.mark.parametrize("dimension", _DIMENSIONS)
def test_compiled_text_matches_iso_source(dimension: str) -> None:
    iso = _iso_texts(dimension)
    compiled = _compiled_texts(dimension)
    drift = {rid: (iso[rid], text) for rid, text in compiled.items() if rid in iso and iso[rid] != text}
    assert not drift, f"{dimension}: recompile with cwe2, drifted ids: {sorted(drift)}"


def test_r_ft_7_defines_a_narrow_fault_isolation_boundary() -> None:
    text = _compiled_texts("reliability")["R-FT-7"].lower()
    assert "fault-isolation boundary" in text
    assert "thread or task entry point" in text
    assert "stack trace" in text
    assert "warning level or above" in text
    assert "partially-updated state" in text
    assert "around ordinary logic is a violation" in text
