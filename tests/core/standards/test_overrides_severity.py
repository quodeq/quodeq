from __future__ import annotations

from quodeq.core.standards.overrides import validate_overrides

DECLARED = {"M-ANA-2": {"max_lines": {"min": 10, "max": 500, "default": 60}}}
KNOWN = frozenset({"M-ANA-2", "S-AUT-3"})


def test_severity_override_on_a_known_requirement_is_accepted():
    clean, errors = validate_overrides({"S-AUT-3": {"severity": "minor"}}, DECLARED, known_requirements=KNOWN)
    assert errors == [] and clean == {"S-AUT-3": {"severity": "minor"}}


def test_severity_and_params_can_coexist():
    clean, errors = validate_overrides({"M-ANA-2": {"max_lines": 80, "severity": "major"}}, DECLARED, known_requirements=KNOWN)
    assert errors == [] and clean == {"M-ANA-2": {"max_lines": 80, "severity": "major"}}


def test_bad_severity_and_unknown_requirement_are_errors():
    _, errors = validate_overrides({"S-AUT-3": {"severity": "blocker"}, "S-NOPE": {"severity": "minor"}}, DECLARED, known_requirements=KNOWN)
    assert any("S-AUT-3.severity" in e for e in errors) and any("S-NOPE" in e for e in errors)
