"""Validation and lookup helpers for discipline definitions."""

from __future__ import annotations

import os

_DEFAULT_CATEGORIES = frozenset({"backend", "frontend", "mobile", "infra"})


def get_valid_categories(categories: str | None = None, env: dict[str, str] | None = None) -> frozenset[str]:
    """Return the set of valid discipline categories.

    *categories* can be provided explicitly, read from the
    ``QUODEQ_DISCIPLINE_CATEGORIES`` env var (comma-separated), or
    defaults to the built-in list.
    """
    if categories is not None:
        return frozenset(categories.split(","))
    from_env = (env or os.environ).get("QUODEQ_DISCIPLINE_CATEGORIES")
    if from_env:
        return frozenset(c.strip() for c in from_env.split(",") if c.strip())
    return _DEFAULT_CATEGORIES
