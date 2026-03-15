"""Utilities for parsing and computing coverage percentages."""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)
_INVALID_COVERAGE_MSG = "Invalid coverage format %r; expected '85%%' or '3/4'"


def parse_coverage_percent(value: str) -> int:
    """Parse a percentage string (e.g. '85%') into an integer."""
    try:
        return int(value.strip().rstrip("%"))
    except ValueError:
        _logger.warning(_INVALID_COVERAGE_MSG, value)
        return 0


def coverage_percent(value: str) -> int:
    """Convert a percentage string or fraction (e.g. '3/4') to an integer percent."""
    if "/" in value:
        num, denom = value.split("/", 1)
        try:
            d = int(denom)
        except ValueError:
            _logger.warning(_INVALID_COVERAGE_MSG, value)
            return 0
        if d == 0:
            return 0
        try:
            return int(round((int(num) / d) * 100))
        except ValueError:
            _logger.warning(_INVALID_COVERAGE_MSG, value)
            return 0
    return parse_coverage_percent(value)
