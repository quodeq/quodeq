"""parse_violations_from_evidence must tolerate a malformed
``principles`` shape without crashing (REL cycle 2 PR 4): a non-dict
top-level ``principles``, a non-dict principle entry, or a non-dict
violation entry must all be dropped, not indexed into."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.finding_builder import ViolationContext
from quodeq.services.violations_parsing import parse_violations_from_evidence


def _ctx() -> ViolationContext:
    return ViolationContext(project="proj", run_id="run-1", dimension="security")


def test_non_dict_principles_yields_no_violations(tmp_path: Path):
    evidence_path = tmp_path / "security_evidence.json"
    evidence_path.write_text(json.dumps({"principles": ["not", "a", "dict"]}), encoding="utf-8")

    result = parse_violations_from_evidence(evidence_path, _ctx())

    assert result is not None
    assert result.violations == []


def test_non_dict_principle_entry_is_skipped(tmp_path: Path):
    evidence_path = tmp_path / "security_evidence.json"
    evidence_path.write_text(json.dumps({
        "principles": {
            "p1": ["not", "a", "dict"],
            "p2": {"display_name": "P2", "violations": [{"file": "a.py", "line": 1}]},
        },
    }), encoding="utf-8")

    result = parse_violations_from_evidence(evidence_path, _ctx())

    assert result is not None
    assert len(result.violations) == 1
    assert result.violations[0].practice_id == "P2"


def test_non_dict_violation_entry_is_skipped(tmp_path: Path):
    evidence_path = tmp_path / "security_evidence.json"
    evidence_path.write_text(json.dumps({
        "principles": {
            "p1": {
                "display_name": "P1",
                "violations": [{"file": "a.py", "line": 1}, "not-a-dict", None],
            },
        },
    }), encoding="utf-8")

    result = parse_violations_from_evidence(evidence_path, _ctx())

    assert result is not None
    assert len(result.violations) == 1


def test_non_list_violations_field_is_skipped(tmp_path: Path):
    """A non-list, truthy ``violations`` value (e.g. an int) must not reach
    the ``for violation in ...`` loop: ``or []`` only substitutes on a
    falsy value, so a non-list truthy value needs its own isinstance check."""
    evidence_path = tmp_path / "security_evidence.json"
    evidence_path.write_text(json.dumps({
        "principles": {
            "p1": {"display_name": "P1", "violations": 5},
        },
    }), encoding="utf-8")

    result = parse_violations_from_evidence(evidence_path, _ctx())

    assert result is not None
    assert result.violations == []


def test_well_formed_evidence_is_unaffected(tmp_path: Path):
    evidence_path = tmp_path / "security_evidence.json"
    evidence_path.write_text(json.dumps({
        "principles": {
            "p1": {"display_name": "P1", "violations": [{"file": "a.py", "line": 1}]},
        },
    }), encoding="utf-8")

    result = parse_violations_from_evidence(evidence_path, _ctx())

    assert result is not None
    assert len(result.violations) == 1
