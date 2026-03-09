"""Discipline detection rules parsed from a .conf file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


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
    elif key in _FILE_KEYS:
        _set_indexed(files, _FILE_KEYS[key], value)
    elif key in _CONTAINS_KEYS:
        _set_indexed(contains, _CONTAINS_KEYS[key], _strip_quotes(value))
    elif key in _CSV_FIELDS:
        kwargs[key] = _parse_csv(value)
    elif key == "detect_priority":
        kwargs["detect_priority"] = _parse_priority(value)
    elif key == "detect_fallback":
        kwargs["detect_fallback"] = value.lower() == "true"


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


def _parse_fields(lines: Iterable[tuple[str, str]]) -> dict:
    """Parse key=value pairs into a kwargs dict for DisciplineRule construction."""
    kwargs: dict = {}
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

    @classmethod
    def from_file(cls, path: Path) -> "DisciplineRegistry":
        """Parse an INI-style disciplines.conf file into a registry."""
        sections: dict[str, list[tuple[str, str]]] = {}
        current_name: str | None = None
        for raw in path.read_text().splitlines():
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
        return sorted(self.disciplines.values(), key=lambda rule: rule.detect_priority)

    def _file_contains(self, path: Path, needle: str) -> bool:
        try:
            return needle in path.read_text(errors="ignore")
        except OSError:
            return False

    def _matches_rule(self, repo: Path, rule: DisciplineRule) -> bool:
        if rule.detect_dir and not (repo / rule.detect_dir).exists():
            return False
        if rule.detect_glob and not any(repo.glob(rule.detect_glob)):
            return False
        if rule.detect_requires_file and not any(repo.glob(rule.detect_requires_file)):
            return False

        for i, file_name in enumerate(rule.detect_files):
            path = repo / file_name
            if not path.exists():
                continue
            needle = rule.detect_contains[i] if i < len(rule.detect_contains) else ""
            if needle:
                if self._file_contains(path, needle):
                    return True
            else:
                return True
        return False

    def detect_matches(self, repo: Path) -> list[str]:
        """Return the names of all disciplines whose rules match the given repo."""
        matches: list[str] = []
        matched_names: set[str] = set()
        for rule in self.iter_disciplines():
            if rule.detect_excludes and any(
                excl in matched_names for excl in rule.detect_excludes
            ):
                continue
            if self._matches_rule(repo, rule):
                matches.append(rule.name)
                matched_names.add(rule.name)
        return matches

    def choose_highest_priority(self, matches: list[str]) -> str:
        """Select the discipline with the lowest (highest-priority) detect_priority value."""
        rules = [self.disciplines[name] for name in matches if name in self.disciplines]
        if not rules:
            return matches[0]
        rules.sort(key=lambda rule: rule.detect_priority)
        return rules[0].name
