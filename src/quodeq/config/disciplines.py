"""Validation and lookup helpers for discipline definitions."""

from __future__ import annotations

from quodeq.config.paths import ConfigPaths
from quodeq.shared.logging import log_error

VALID_CATEGORIES = frozenset({"backend", "frontend", "mobile", "infra"})


def validate_new_discipline(name: str, language: str, category: str) -> int:
    """Validate that name, language, and category are acceptable for a new discipline."""
    if not name or not language:
        log_error(
            "Usage: add-discipline <name> <language> [--category=<backend|frontend|mobile|infra>]"
        )
        return 1
    if category not in VALID_CATEGORIES:
        log_error(f"Invalid category '{category}'. Must be: backend, frontend, mobile, or infra")
        return 1
    return 0


def get_discipline_language(name: str, paths: ConfigPaths) -> str | None:
    """Look up the programming language configured for a discipline."""
    conf = paths.root / "config" / "disciplines.conf"
    if not conf.exists():
        return None
    current = None
    try:
        conf_lines = conf.read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    for line in conf_lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            continue
        if current == name and line.startswith("language="):
            return line.split("=", 1)[1].strip()
    return None
