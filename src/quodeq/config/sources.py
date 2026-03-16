"""Validation of source-citation tables in practice markdown files."""

from __future__ import annotations

_SOURCES_COLUMN_HEADER = "| Sources |"
_TIER_COLUMN_HEADER = "| Tier |"


def has_required_sources_table(markdown: str) -> bool:
    """Check whether a markdown string contains the required Sources and Tier columns."""
    return _SOURCES_COLUMN_HEADER in markdown and _TIER_COLUMN_HEADER in markdown
