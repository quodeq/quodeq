"""Severity ordering and the lenient parser findings arrive through."""
import pytest

from quodeq.core.types.severity import SEVERITY_ORDER, Severity, parse_severity


def test_order_is_most_severe_first():
    assert SEVERITY_ORDER == (Severity.CRITICAL, Severity.MAJOR, Severity.MINOR)


@pytest.mark.parametrize("raw,expected", [
    ("critical", Severity.CRITICAL), ("MAJOR", Severity.MAJOR), (" minor ", Severity.MINOR),
    (None, Severity.MINOR), ("", Severity.MINOR), ("bogus", Severity.MINOR),
])
def test_parse_severity_defaults_to_minor(raw, expected):
    assert parse_severity(raw) is expected


def test_parse_severity_custom_default():
    assert parse_severity("bogus", default=Severity.MAJOR) is Severity.MAJOR
