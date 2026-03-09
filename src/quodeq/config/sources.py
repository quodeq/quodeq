from __future__ import annotations


def has_required_sources_table(markdown: str) -> bool:
    return "| Sources |" in markdown and "| Tier |" in markdown
