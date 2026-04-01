"""Validation and lookup helpers for discipline definitions."""

from __future__ import annotations

import os

from quodeq.config.discipline_registry import DisciplineRegistry
from quodeq.config.paths import ConfigPaths
# NOTE: logging in inner layer — tracked for middleware extraction
from quodeq.shared.logging import log_error, log_warning

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


def validate_new_discipline(
    name: str,
    language: str,
    category: str,
    valid_categories: frozenset[str] | None = None,
) -> int:
    """Validate that name, language, and category are acceptable for a new discipline.

    *valid_categories* overrides the env-var lookup when provided,
    allowing callers to pass fresh env-var values or test values.
    """
    cats = valid_categories if valid_categories is not None else get_valid_categories()
    if not name or not language:
        log_error(
            f"Usage: add-discipline <name> <language> [--category=<{'|'.join(sorted(cats))}>]"
        )
        return 1
    if category not in cats:
        log_error(f"Invalid category '{category}'. Must be one of: {', '.join(sorted(cats))}")
        return 1
    return 0


def get_discipline_language(name: str, paths: ConfigPaths) -> str | None:
    """Look up the programming language configured for a discipline."""
    conf = paths.disciplines_conf
    if not conf.exists():
        return None
    try:
        registry = DisciplineRegistry.from_file(conf)
    except ValueError as exc:
        log_warning(str(exc))
        return None
    rule = registry.disciplines.get(name)
    if rule is None:
        return None
    return rule.language
