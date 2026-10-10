"""The standard's suggested severity for a requirement, as shown to the model.

The grade never reads it. The model starts from it and decides the impact of
each instance; the evaluation rules say how. A project's override for the
requirement replaces the standard's suggestion.
"""
from __future__ import annotations

from collections.abc import Mapping

from quodeq.core.standards.overrides import SEVERITY_KEY
from quodeq.core.types.severity import is_severity


def advised_severity(req: object, override: Mapping | None = None) -> str | None:
    """The ladder value the prompt shows for *req*: the override's if valid, else the requirement's."""
    if isinstance(override, Mapping) and is_severity(override.get(SEVERITY_KEY)):
        return str(override[SEVERITY_KEY])
    if not isinstance(req, Mapping):
        return None
    value = req.get(SEVERITY_KEY)
    return str(value) if is_severity(value) else None
