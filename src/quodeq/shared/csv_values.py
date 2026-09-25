"""Comma-separated settings (env vars, front matter, query strings) as item lists."""
from __future__ import annotations


def split_csv(value: str) -> list[str]:
    """The trimmed items of the comma-separated *value*, in order, blanks dropped."""
    return [item.strip() for item in value.split(",") if item.strip()]
