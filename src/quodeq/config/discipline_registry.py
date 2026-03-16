"""Discipline detection rules parsed from a .conf file."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any, Iterable

from quodeq.shared.utils import read_text

_logger = logging.getLogger(__name__)


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
    detect_excludes: list[str] | None = None
    detect_fallback: bool = False
    suggested_topics: list[str] | None = None


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


def _parse_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


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


def _parse_fields(lines: Iterable[tuple[str, str]]) -> dict[str, Any]:
    """Parse key=value pairs into a kwargs dict for DisciplineRule construction."""
    kwargs: dict[str, Any] = {}
    files: list[str | None] = []
    contains: list[str | None] = []
    for key, value in lines:
        _dispatch_field(key, value, kwargs, files, contains)
    _pad_and_finalize(files, contains, kwargs)
    return kwargs


@dataclass
class DisciplineRegistry:
    """Collection of discipline rules loaded from a configuration file."""

    disciplines: dict[str, DisciplineRule]

    def __post_init__(self) -> None:
        self._sorted_disciplines: list[DisciplineRule] = sorted(
            self.disciplines.values(), key=lambda rule: rule.detect_priority
        )
        self._file_cache: dict[Path, str] = {}

    @classmethod
    def from_file(cls, path: Path) -> "DisciplineRegistry":
        """Parse an INI-style disciplines.conf file into a registry."""
        sections: dict[str, list[tuple[str, str]]] = {}
        current_name: str | None = None
        try:
            lines = read_text(path).splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(
                f"Cannot read disciplines config {path}: {exc}. "
                f"Check file permissions or run 'quodeq configure' to regenerate."
            ) from exc
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current_name = line[1:-1]
                sections[current_name] = []
                continue
            if current_name is None or "=" not in line:
                continue
            key, value = line.split("=", 1)
            sections[current_name].append((key.strip(), value.strip()))

        rules: dict[str, DisciplineRule] = {}
        for name, kvs in sections.items():
            kwargs = _parse_fields(kvs)
            rules[name] = DisciplineRule(name=name, **kwargs)

        return cls(rules)

    def iter_disciplines(self) -> Iterable[DisciplineRule]:
        """Yield all discipline rules sorted by detection priority."""
        return self._sorted_disciplines

    def _file_contains(self, path: Path, needle: str) -> bool:
        try:
            content = self._file_cache.get(path)
            if content is None:
                content = read_text(path, errors="ignore")
                self._file_cache[path] = content
            return needle in content
        except OSError as exc:
            _logger.debug("Could not read %s for content check: %s", path, exc)
            return False

    def _check_prerequisites(self, repo: Path, rule: DisciplineRule) -> bool:
        """Return False if any directory/glob/required-file prerequisite is unmet."""
        if rule.detect_dir and not (repo / rule.detect_dir).exists():
            return False
        if rule.detect_glob and not any(repo.glob(rule.detect_glob)):
            return False
        if rule.detect_requires_file and not any(repo.glob(rule.detect_requires_file)):
            return False
        return True

    def _any_detect_file_matches(self, repo: Path, rule: DisciplineRule) -> bool:
        """Return True if any detect_file matches (with optional content check)."""
        for i, file_name in enumerate(rule.detect_files):
            path = repo / file_name
            if not path.exists():
                continue
            needle = rule.detect_contains[i] if i < len(rule.detect_contains) else ""
            if not needle or self._file_contains(path, needle):
                return True
        return False

    def _matches_rule(self, repo: Path, rule: DisciplineRule) -> bool:
        if not self._check_prerequisites(repo, rule):
            return False
        return self._any_detect_file_matches(repo, rule)

    def detect_matches(self, repo: Path) -> list[str]:
        """Return the names of all disciplines whose rules match the given repo.

        Fallback-only disciplines (``detect_fallback=True``) are only included
        when no non-fallback discipline matched.
        """
        matches: list[str] = []
        fallback_matches: list[str] = []
        matched_names: set[str] = set()
        for rule in self.iter_disciplines():
            if rule.detect_excludes and any(
                excl in matched_names for excl in rule.detect_excludes
            ):
                continue
            if self._matches_rule(repo, rule):
                if rule.detect_fallback:
                    fallback_matches.append(rule.name)
                else:
                    matches.append(rule.name)
                    matched_names.add(rule.name)
        return matches if matches else fallback_matches

    def choose_highest_priority(self, matches: list[str]) -> str:
        """Select the discipline with the lowest (highest-priority) detect_priority value."""
        if not matches:
            raise ValueError("No matches to choose from")
        match_set = set(matches)
        for rule in self._sorted_disciplines:
            if rule.name in match_set:
                return rule.name
        return matches[0]
