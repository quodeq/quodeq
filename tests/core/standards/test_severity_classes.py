"""The severity ladder a standard may suggest per requirement."""
from quodeq.core.standards.severity_classes import is_severity_class


def test_is_severity_class():
    assert is_severity_class("minor") and is_severity_class("major") and is_severity_class("critical")
    assert not is_severity_class("blocker") and not is_severity_class(None) and not is_severity_class(3)
