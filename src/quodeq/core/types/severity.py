"""Finding severity vocabulary."""
from __future__ import annotations

from enum import StrEnum


class Severity(StrEnum):
    """How bad one finding is; the value is what findings carry on the wire."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


# Most severe first; the order every ranking and bucket in the app uses.
SEVERITY_ORDER: tuple[Severity, ...] = (Severity.CRITICAL, Severity.MAJOR, Severity.MINOR)


def parse_severity(raw: str | None, default: Severity = Severity.MINOR) -> Severity:
    """The ``Severity`` a reported string means; unknown or empty input is ``default``.

    Lenient on purpose: severities arrive from model output, and a finding
    with a misspelled severity is still a finding.
    """
    try:
        return Severity((raw or "").strip().lower())
    except ValueError:
        return default
