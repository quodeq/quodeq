"""Validation and lookup helpers for discipline definitions."""

from __future__ import annotations

from quodeq.config.paths import ConfigPaths
from quodeq.shared.logging import log_error, log_warning

_DEFAULT_CATEGORIES = "backend,frontend,mobile,infra"


def get_valid_categories(categories: str | None = None) -> frozenset[str]:
    """Return the set of valid discipline categories.

    *categories* must be provided by the caller; defaults to the built-in
    list when ``None``.
    """
    raw = categories if categories is not None else _DEFAULT_CATEGORIES
    return frozenset(raw.split(","))


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
    from quodeq.config.discipline_registry import DisciplineRegistry

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
