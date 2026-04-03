"""DisciplineRule dataclass and minimal string helpers."""

from __future__ import annotations

from dataclasses import dataclass


_DEFAULT_DETECT_PRIORITY = 99  # lowest priority — used as fallback catch-all


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and (
        (value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")
    ):
        return value[1:-1]
    return value


@dataclass(frozen=True)
class DisciplineRule:
    """A single discipline's detection criteria and metadata."""

    name: str
    language: str | None = None
    category: str | None = None
    detect_files: tuple[str, ...] = ()
    detect_contains: tuple[str, ...] = ()
    detect_glob: str | None = None
    detect_dir: str | None = None
    detect_requires_file: str | None = None
    detect_priority: int = _DEFAULT_DETECT_PRIORITY
    detect_excludes: tuple[str, ...] | None = None
    detect_fallback: bool = False
    suggested_topics: tuple[str, ...] | None = None
