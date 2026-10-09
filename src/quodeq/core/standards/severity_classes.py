"""Severity classes: what the standard says a broken rule is worth.

Pure helpers over a compiled-standards dict and a project's overrides
mapping. Loading from disk lives in ``data/fs/standards_loader`` and
``data/fs/severity_classes_store``.
"""
from __future__ import annotations

from collections.abc import Mapping

from quodeq.core.types.severity import Severity

SEVERITY_KEY = "severity"
_LADDER = frozenset({Severity.MINOR, Severity.MAJOR, Severity.CRITICAL})


def is_severity_class(value: object) -> bool:
    """True for the three ladder words, and nothing else."""
    return isinstance(value, str) and value in _LADDER


def extract_severity_classes(data: Mapping) -> dict[str, str]:
    """``{req_id: class}`` for every requirement that declares a ladder value."""
    classes: dict[str, str] = {}
    principles = data.get("principles") if isinstance(data, Mapping) else None
    if not isinstance(principles, list):
        return classes
    for principle in principles:
        requirements = principle.get("requirements") if isinstance(principle, Mapping) else None
        if not isinstance(requirements, list):
            continue
        for req in requirements:
            if not isinstance(req, Mapping):
                continue
            req_id = req.get("id")
            value = req.get(SEVERITY_KEY)
            if isinstance(req_id, str) and req_id and is_severity_class(value):
                classes[req_id] = str(value)
    return classes


def apply_severity_overrides(
    classes: Mapping[str, str], overrides: Mapping[str, Mapping],
) -> dict[str, str]:
    """*classes* with each ``overrides[req]["severity"]`` ladder value applied; junk ignored."""
    merged = dict(classes)
    for req_id, values in overrides.items():
        if not isinstance(values, Mapping):
            continue
        value = values.get(SEVERITY_KEY)
        if is_severity_class(value):
            merged[str(req_id)] = str(value)
    return merged
