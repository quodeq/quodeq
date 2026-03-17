from __future__ import annotations

from quodeq.analysis.plugins.schema_validator import (
    validate_dimensions,
)


# ── dimensions.json ───────────────────────────────────────────────────

def _valid_dimensions():
    return {
        "applies": [
            {"id": "security", "weight": 1.2, "iso_25010": "Security", "source": "OWASP"},
        ],
        "excludes": ["usability"],
    }


def test_valid_dimensions():
    assert validate_dimensions(_valid_dimensions()) == []


def test_dimensions_without_optional_fields():
    data = {"applies": [{"id": "maintainability", "weight": 1.0}]}
    assert validate_dimensions(data) == []


def test_dimensions_missing_applies():
    assert validate_dimensions({}) != []


def test_dimensions_missing_weight():
    data = {"applies": [{"id": "security"}]}
    assert validate_dimensions(data) != []
