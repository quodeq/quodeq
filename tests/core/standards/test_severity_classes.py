"""Severity classes come out of a compiled standard and bend to a project's overrides."""
from __future__ import annotations

from quodeq.core.standards.severity_classes import (
    apply_severity_overrides, extract_severity_classes, is_severity_class,
)

COMPILED = {
    "principles": [
        {"name": "Integrity", "requirements": [
            {"id": "S-INT-2", "severity": "critical"},
            {"id": "S-INT-1", "severity": "major"},
            {"id": "S-INT-9", "severity": None},
            {"id": "S-INT-8", "severity": "blocker"},
            {"severity": "minor"},
        ]},
    ],
}


def test_extract_keeps_only_ladder_values_with_an_id():
    assert extract_severity_classes(COMPILED) == {"S-INT-2": "critical", "S-INT-1": "major"}


def test_extract_tolerates_malformed_payloads():
    assert extract_severity_classes({}) == {}
    assert extract_severity_classes({"principles": "nope"}) == {}
    assert extract_severity_classes({"principles": [{"requirements": "nope"}]}) == {}


def test_is_severity_class():
    assert is_severity_class("minor") and is_severity_class("major") and is_severity_class("critical")
    assert not is_severity_class("blocker") and not is_severity_class(None) and not is_severity_class(3)


def test_overrides_lower_or_raise_a_class_and_ignore_junk():
    classes = {"S-INT-2": "critical", "S-INT-1": "major"}
    out = apply_severity_overrides(classes, {
        "S-INT-2": {"severity": "major"},        # a desktop tool lowers it for its context
        "S-INT-1": {"max_lines": 60},            # numeric param override, not a class
        "S-AUT-3": {"severity": "minor"},        # unclassed rule gets a class from the project
        "S-INT-9": {"severity": "blocker"},      # junk ignored
        "S-INT-8": "minor",                      # not an object, ignored
    })
    assert out == {"S-INT-2": "major", "S-INT-1": "major", "S-AUT-3": "minor"}
    assert classes == {"S-INT-2": "critical", "S-INT-1": "major"}  # input untouched
