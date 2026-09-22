"""Shared coercions for optional per-finding wire fields."""
from __future__ import annotations

from quodeq.core.finding_coercions import coerce_confidence, coerce_scope_downgrade


def test_confidence_clamps_and_defaults():
    assert coerce_confidence(None) == 100
    assert coerce_confidence(None, default=50) == 50
    assert coerce_confidence("x") == 100
    assert coerce_confidence(-5) == 0
    assert coerce_confidence(250) == 100
    assert coerce_confidence("42") == 42
    assert coerce_confidence(7.9) == 7


def test_scope_downgrade_accepts_only_string_dicts():
    marker = {"rule": "r", "from": "major", "to": "minor"}
    assert coerce_scope_downgrade(marker) == marker
    assert coerce_scope_downgrade({"rule": 1}) is None
    assert coerce_scope_downgrade("major") is None
    assert coerce_scope_downgrade(None) is None
    assert coerce_scope_downgrade({}) == {}
