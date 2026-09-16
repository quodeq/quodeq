"""Every shipped compiled standards file must extract a valid (possibly empty) taxonomy.

PR B adds the requirement that every graded requirement declares at least
one code; this walk already catches a malformed block before it ships.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.core.taxonomy import extract_taxonomy

COMPILED = Path(__file__).resolve().parents[2] / "src" / "quodeq" / "data" / "standards" / "compiled"

_FILES = sorted(COMPILED.glob("*.json"))
assert _FILES, f"no compiled standards under {COMPILED}"


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.stem)
def test_shipped_compiled_standards_have_valid_taxonomy(path):
    extract_taxonomy(json.loads(path.read_text(encoding="utf-8")))  # must not raise
