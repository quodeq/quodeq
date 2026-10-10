"""Severity ordering and the lenient parser findings arrive through."""
import pytest

from quodeq.core.types.severity import SEVERITY_ORDER, Severity, is_severity, parse_severity


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


def test_is_severity_accepts_exactly_the_three_words():
    assert is_severity("minor") and is_severity("major") and is_severity("critical")
    assert not is_severity("blocker") and not is_severity("Major") and not is_severity(None) and not is_severity(3)
