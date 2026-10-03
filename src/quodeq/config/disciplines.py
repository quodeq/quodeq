"""Validation and lookup helpers for discipline definitions."""

from __future__ import annotations

from quodeq.shared.env_resolve import resolve_env
from quodeq.shared.csv_values import split_csv

_DEFAULT_CATEGORIES = frozenset({"backend", "frontend", "mobile", "infra"})


def get_valid_categories(categories: str | None = None, env: dict[str, str] | None = None) -> frozenset[str]:
    """Return the set of valid discipline categories.

    *categories* can be provided explicitly, read from the
    ``QUODEQ_DISCIPLINE_CATEGORIES`` env var (comma-separated), or
    defaults to the built-in list.
    """
    if categories is not None:
        return frozenset(split_csv(categories))
    from_env = resolve_env(env).get("QUODEQ_DISCIPLINE_CATEGORIES")
    if from_env:
        return frozenset(split_csv(from_env))
    return _DEFAULT_CATEGORIES
