"""INI-style conf parsing helpers for discipline rules."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Iterable

from quodeq.config._discipline_rule import _DEFAULT_DETECT_PRIORITY, _strip_quotes

# Conf keys that map to indexed positions in detect_files / detect_contains
_FILE_KEYS = {"detect_file": 0, "detect_file_alt": 1, "detect_file_alt2": 2}
_CONTAINS_KEYS = {"detect_contains": 0, "detect_contains_alt": 1, "detect_contains_alt2": 2}

_SIMPLE_FIELDS = {
    "language", "category", "detect_glob", "detect_dir", "detect_requires_file",
}
_CSV_FIELDS = {"detect_excludes", "suggested_topics"}
_SPECIAL_HANDLERS: dict[str, Callable[[str], int | bool]] = {
    "detect_priority": lambda v: _parse_priority(v),
    "detect_fallback": lambda v: v.lower() == "true",
}


def _parse_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _set_indexed(lst: list[str | None], index: int, value: str) -> None:
    """Ensure *lst* has at least *index+1* slots and set the value."""
    while len(lst) < index + 1:
        lst.append(None)
    lst[index] = value


def _parse_priority(value: str) -> int:
    """Parse a detect_priority value, falling back to the default."""
    try:
        return int(value)
    except ValueError:
        return _DEFAULT_DETECT_PRIORITY


def _dispatch_field(
    key: str,
    value: str,
    kwargs: dict,
    files: list[str | None],
    contains: list[str | None],
) -> None:
    """Apply one key=value pair to the accumulator kwargs / files / contains lists."""
    if key in _SIMPLE_FIELDS:
        kwargs[key] = value
        return
    if key in _FILE_KEYS:
        _set_indexed(files, _FILE_KEYS[key], value)
        return
    if key in _CONTAINS_KEYS:
        _set_indexed(contains, _CONTAINS_KEYS[key], _strip_quotes(value))
        return
    if key in _CSV_FIELDS:
        kwargs[key] = _parse_csv(value)
        return
    handler = _SPECIAL_HANDLERS.get(key)
    if handler is not None:
        kwargs[key] = handler(value)


def _pad_and_finalize(files: list[str | None], contains: list[str | None], kwargs: dict) -> None:
    """Pad file/contains lists to equal length and write the tuples into kwargs."""
    max_len = max(len(files), len(contains))
    while len(files) < max_len:
        files.append(None)
    while len(contains) < max_len:
        contains.append(None)
    kwargs["detect_files"] = tuple(f for f in files if f is not None)
    kwargs["detect_contains"] = tuple(
        c for c in contains[:max_len] if c is not None
    )


def parse_fields(lines: Iterable[tuple[str, str]]) -> dict[str, Any]:
    """Parse key=value pairs into a kwargs dict for DisciplineRule construction."""
    kwargs: dict[str, Any] = {}
    files: list[str | None] = []
    contains: list[str | None] = []
    for key, value in lines:
        _dispatch_field(key, value, kwargs, files, contains)
    _pad_and_finalize(files, contains, kwargs)
    return kwargs
