"""Finding type vocabulary: what one finding says about a requirement."""
from __future__ import annotations

from enum import StrEnum


class FindingType(StrEnum):
    """A finding's type: the ``t`` field of a finding dict and ``Judgment.verdict``.

    The values are what evidence JSONL, the ``verdict`` column of
    ``evaluation.db`` and the MCP ``report_finding`` schema carry.
    "dismissed" is not a finding type; it is a view-only state on ``Finding``.
    """

    VIOLATION = "violation"
    COMPLIANCE = "compliance"


# Membership test for raw values read from disk or model output. A tuple, not
# a frozenset, so an unhashable value (a list where a string belongs) tests
# False instead of raising TypeError.
FINDING_TYPES: tuple[FindingType, ...] = tuple(FindingType)


def parse_finding_type(raw: object) -> FindingType | None:
    """The ``FindingType`` a model-reported value means, or None.

    Lenient on case and surrounding space only, like ``parse_severity``: a
    model that writes ``"Violation"`` still reported a violation. The plural
    ``"violations"`` is a report bucket key, never a finding type, so it is
    not accepted.
    """
    if not isinstance(raw, str):
        return None
    try:
        return FindingType(raw.strip().lower())
    except ValueError:
        return None
