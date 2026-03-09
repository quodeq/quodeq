"""Utilities for parsing and computing coverage percentages."""

_PERCENT_MULTIPLIER = 100


def parse_coverage_percent(value: str) -> int:
    """Parse a percentage string (e.g. '85%') into an integer."""
    return int(value.strip().rstrip("%"))


def coverage_percent(value: str) -> int:
    """Convert a percentage string or fraction (e.g. '3/4') to an integer percent."""
    if "/" in value:
        num, denom = value.split("/", 1)
        return int(round((int(num) / int(denom)) * _PERCENT_MULTIPLIER))
    return parse_coverage_percent(value)
