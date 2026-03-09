"""Validation of source-citation tables in practice markdown files."""

from __future__ import annotations


def has_required_sources_table(markdown: str) -> bool:
    """Check whether a markdown string contains the required Sources and Tier columns."""
    return "| Sources |" in markdown and "| Tier |" in markdown
