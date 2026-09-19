"""build_finding coerces scope_downgrade with the shared core coercion."""
from __future__ import annotations

import pytest

from quodeq.data.fs.report_parser._report_parsing import build_finding

_MARKER = {"rule": "sourceless_path", "from": "major", "to": "minor"}


def test_well_formed_marker_is_carried():
    finding = build_finding({"principle": "P1", "scope_downgrade": _MARKER}, include_severity=True)
    assert finding.scope_downgrade == _MARKER


def test_missing_marker_is_none():
    assert build_finding({"principle": "P1"}, include_severity=True).scope_downgrade is None


@pytest.mark.parametrize("raw", ["not-a-dict", 7, ["rule"]])
def test_non_dict_marker_is_dropped(raw):
    finding = build_finding({"principle": "P1", "scope_downgrade": raw}, include_severity=True)
    assert finding.scope_downgrade is None


def test_dict_with_non_string_values_is_dropped():
    """The scope gate only ever stamps strings; anything else is corrupt input.

    The restore path reads ``from`` off this marker and writes it straight to
    ``severity``, so a non-string value must not reach it.
    """
    finding = build_finding(
        {"principle": "P1", "scope_downgrade": {"rule": "x", "from": 1, "to": "minor"}},
        include_severity=True,
    )
    assert finding.scope_downgrade is None
