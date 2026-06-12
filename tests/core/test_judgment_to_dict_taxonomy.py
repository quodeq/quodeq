"""Regression: judgment_to_dict must emit the 'vt' key the scorer groups by.

The scoring tally (core/scoring/_tallies.py) detects the violation taxonomy
via item.get("vt"). If judgment_to_dict only emits "violation_type", taxonomy
grouping silently disables on the production parse->score path.
"""
from __future__ import annotations

from quodeq.core.events.models import Judgment
from quodeq.core.evidence._jsonl import judgment_to_dict
from quodeq.core.scoring._tallies import evidence_has_taxonomy


def _violation(vt: str | None) -> Judgment:
    return Judgment(
        practice_id="ts-001", verdict="violation", dimension="security",
        file="src/app.ts", line=10, reason="eval is dangerous",
        severity="critical", violation_type=vt,
    )


def test_judgment_to_dict_emits_vt_key():
    d = judgment_to_dict(_violation("code-injection"))
    assert d["vt"] == "code-injection"
    # Keep the long key too: the UI/report read 'violation_type'.
    assert d["violation_type"] == "code-injection"


def test_scorer_detects_taxonomy_from_judgment_to_dict_output():
    dicts = [judgment_to_dict(_violation("code-injection"))]
    assert evidence_has_taxonomy(dicts) is True


def test_no_vt_key_when_violation_type_absent():
    d = judgment_to_dict(_violation(None))
    assert "vt" not in d
    assert "violation_type" not in d
