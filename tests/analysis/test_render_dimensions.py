"""render_dimensions must raise a clear ValueError on malformed data, matching
this module's convention (render_compiled_standards / render_compact_standards
both raise ValueError for a missing required 'id'), instead of a bare KeyError.
"""
from __future__ import annotations

import pytest

from quodeq.analysis.prompts._renderers import render_dimensions


def test_dimension_missing_id_raises_value_error() -> None:
    dimensions_data = {
        "applies": [
            {"source": "no id here"},  # malformed: missing required 'id'
            {"id": "security", "weight": 2.0},
        ]
    }

    with pytest.raises(ValueError, match="missing required 'id'"):
        render_dimensions(dimensions_data, "security")


def test_valid_dimension_still_renders() -> None:
    dimensions_data = {
        "applies": [
            {"id": "security", "weight": 2.0, "source": "OWASP"},
        ]
    }

    out = render_dimensions(dimensions_data, "security")
    assert "**Dimension:** security" in out
    assert "**Weight:** 2.0" in out


def test_unknown_dimension_returns_not_configured_message() -> None:
    dimensions_data = {"applies": [{"id": "security"}]}

    out = render_dimensions(dimensions_data, "performance")
    assert "not configured" in out
