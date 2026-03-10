"""Utilities for parsing and computing coverage percentages."""

from __future__ import annotations


def parse_coverage_percent(value: str) -> int:
    """Parse a percentage string (e.g. '85%') into an integer."""
    return int(value.strip().rstrip("%"))


def coverage_percent(value: str) -> int:
    """Convert a percentage string or fraction (e.g. '3/4') to an integer percent."""
    if "/" in value:
        num, denom = value.split("/", 1)
        return int(round((int(num) / int(denom)) * 100))
    return parse_coverage_percent(value)
