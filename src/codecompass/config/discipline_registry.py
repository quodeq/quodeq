from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and (
        (value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")
    ):
        return value[1:-1]
    return value


@dataclass
class DisciplineRule:
    name: str
    language: str | None = None
    category: str | None = None
    detect_file: str | None = None
    detect_contains: str | None = None
    detect_file_alt: str | None = None
    detect_contains_alt: str | None = None
    detect_file_alt2: str | None = None
    detect_contains_alt2: str | None = None
    detect_glob: str | None = None
    detect_dir: str | None = None
    detect_requires_file: str | None = None
    detect_priority: int = 99
    detect_excludes: list[str] | None = None
    detect_fallback: bool = False
    suggested_topics: list[str] | None = None


@dataclass
class DisciplineRegistry:
    disciplines: dict[str, DisciplineRule]

    @classmethod
    def from_file(cls, path: Path) -> "DisciplineRegistry":
        current = None
        rules: dict[str, DisciplineRule] = {}
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                name = line[1:-1]
                current = DisciplineRule(name=name)
                rules[name] = current
                continue
            if not current or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key == "language":
                current.language = value
            elif key == "category":
                current.category = value
            elif key == "detect_file":
                current.detect_file = value
            elif key == "detect_contains":
                current.detect_contains = _strip_quotes(value)
            elif key == "detect_file_alt":
                current.detect_file_alt = value
            elif key == "detect_contains_alt":
                current.detect_contains_alt = _strip_quotes(value)
            elif key == "detect_file_alt2":
                current.detect_file_alt2 = value
            elif key == "detect_contains_alt2":
                current.detect_contains_alt2 = _strip_quotes(value)
            elif key == "detect_glob":
                current.detect_glob = value
            elif key == "detect_dir":
                current.detect_dir = value
            elif key == "detect_requires_file":
                current.detect_requires_file = value
            elif key == "detect_priority":
                try:
                    current.detect_priority = int(value)
                except ValueError:
                    current.detect_priority = 99
            elif key == "detect_excludes":
                current.detect_excludes = [
                    part.strip() for part in value.split(",") if part.strip()
                ]
            elif key == "detect_fallback":
                current.detect_fallback = value.lower() == "true"
            elif key == "suggested_topics":
                current.suggested_topics = [
                    part.strip() for part in value.split(",") if part.strip()
                ]

        return cls(rules)

    def iter_disciplines(self) -> Iterable[DisciplineRule]:
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

        def match_file(file_name: str | None, contains: str | None) -> bool:
            if not file_name:
                return False
            path = repo / file_name
            if not path.exists():
                return False
            if contains:
                return self._file_contains(path, contains)
            return True

        if match_file(rule.detect_file, rule.detect_contains):
            return True
        if match_file(rule.detect_file_alt, rule.detect_contains_alt):
            return True
        if match_file(rule.detect_file_alt2, rule.detect_contains_alt2):
            return True
        return False

    def detect_matches(self, repo: Path) -> list[str]:
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
        rules = [self.disciplines[name] for name in matches if name in self.disciplines]
        if not rules:
            return matches[0]
        rules.sort(key=lambda rule: rule.detect_priority)
        return rules[0].name
