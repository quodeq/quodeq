"""DisciplineRegistry: repo discipline detection with file-content matching."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from quodeq.shared.utils import read_text
from quodeq.config._dependency_parsers import get_structured_matcher
from quodeq.config._discipline_rule import DisciplineRule
from quodeq.config._discipline_conf_loader import load_disciplines_from_file

_logger = logging.getLogger(__name__)
_FILE_CACHE_MAX = 256


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
        return cls(load_disciplines_from_file(path))

    def iter_disciplines(self) -> Iterable[DisciplineRule]:
        """Yield all discipline rules sorted by detection priority."""
        return self._sorted_disciplines

    def _read_cached(self, path: Path) -> str | None:
        try:
            content = self._file_cache.get(path)
            if content is None:
                if len(self._file_cache) >= _FILE_CACHE_MAX:
                    self._file_cache.pop(next(iter(self._file_cache)))
                content = read_text(path, errors="ignore")
                self._file_cache[path] = content
            return content
        except OSError as exc:
            _logger.debug("Could not read %s for content check: %s", path, exc)
            return None

    def _file_matches(self, path: Path, needle: str) -> bool:
        """Check whether *path* satisfies *needle*.

        Empty needle means "no content check, file presence is enough." For files we
        recognise as dependency manifests (pyproject.toml, package.json, Cargo.toml,
        go.mod, composer.json, requirements.txt), match against the parsed dependency
        list — not a raw substring — to avoid false positives from comments, names of
        unrelated packages (e.g. ``preact`` containing ``react``), or descriptions.
        """
        if not needle:
            return True
        content = self._read_cached(path)
        if content is None:
            return False
        matcher = get_structured_matcher(path.name)
        if matcher is not None:
            return matcher(content, needle)
        return needle in content

    def _check_prerequisites(self, repo: Path, rule: DisciplineRule) -> bool:
        if rule.detect_dir and not (repo / rule.detect_dir).exists():
            return False
        if rule.detect_glob and not any(repo.glob(rule.detect_glob)):
            return False
        return not (rule.detect_requires_file and not any(repo.glob(rule.detect_requires_file)))

    def _any_detect_file_matches(self, repo: Path, rule: DisciplineRule) -> bool:
        for i, file_name in enumerate(rule.detect_files):
            path = repo / file_name
            if not path.exists():
                continue
            needle = rule.detect_contains[i] if i < len(rule.detect_contains) else ""
            if self._file_matches(path, needle):
                return True
        return False

    def _matches_rule(self, repo: Path, rule: DisciplineRule) -> bool:
        return self._check_prerequisites(repo, rule) and self._any_detect_file_matches(repo, rule)

    def detect_matches(self, repo: Path) -> list[str]:
        """Return discipline names matching the repo. Fallbacks only if no primary match."""
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
        """Select the discipline with the lowest detect_priority value."""
        if not matches:
            raise ValueError("No matches to choose from")
        match_set = set(matches)
        for rule in self._sorted_disciplines:
            if rule.name in match_set:
                return rule.name
        return matches[0]
