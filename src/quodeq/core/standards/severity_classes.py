"""The severity ladder a standard may suggest per requirement.

A requirement's ``severity`` is a suggestion the model reads in its checklist
(see ``analysis/prompts/severity_advice``); the grade never applies it.
"""
from __future__ import annotations

from quodeq.core.types.severity import Severity

SEVERITY_KEY = "severity"
_LADDER = frozenset({Severity.MINOR, Severity.MAJOR, Severity.CRITICAL})


def is_severity_class(value: object) -> bool:
    """True for the three ladder words, and nothing else."""
    return isinstance(value, str) and value in _LADDER
