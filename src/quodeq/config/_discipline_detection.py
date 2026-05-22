"""DisciplineRegistry: repo discipline detection with file-content matching."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Iterable

from quodeq.shared.utils import read_text
from quodeq.config._dependency_parsers import get_structured_matcher
from quodeq.config._discipline_rule import DisciplineRule
from quodeq.config._discipline_conf_loader import load_disciplines_from_file

_logger = logging.getLogger(__name__)
_FILE_CACHE_MAX = 256

# Directories never recursed into when discovering subproject roots in a
# monorepo. Mirrors detection.json's skip_dirs plus a few more dependency caches.
# Hidden dirs (those starting with '.') are also skipped.
_SUBPROJECT_SKIP_DIRS: frozenset[str] = frozenset({
    "node_modules", "vendor", "venv", ".venv", "__pycache__",
    "dist", "build", "out", ".next", "target", "static",
    ".git", ".svn", ".hg", ".tox", ".mypy_cache", ".pytest_cache",
})

# How deep to walk when looking for subproject roots. Caps cost on huge repos.
_DEFAULT_MAX_DEPTH = 4


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
    def from_file(cls, path: Path, *, strict: bool = False) -> "DisciplineRegistry":
        """Parse an INI-style disciplines.conf file into a registry.

        Surfaces issues (unknown keys, dangling ``detect_excludes`` references,
        rules with no triggers) found during load. With ``strict=True`` any issue
        raises ``ValueError`` — use this in CI against the bundled conf so typos
        cannot ship. Without ``strict`` issues are logged as warnings and the
        registry loads as usual (preserves user-facing tolerance).
        """
        rules, parse_problems = load_disciplines_from_file(path)
        registry = cls(rules)
        problems = parse_problems + registry.validate()
        if problems:
            if strict:
                raise ValueError(
                    f"disciplines config {path} has issues:\n  - "
                    + "\n  - ".join(problems)
                )
            for p in problems:
                _logger.warning("disciplines.conf: %s", p)
        return registry

    def validate(self) -> list[str]:
        """Return a list of human-readable issues discovered in the loaded rules.

        Currently catches:

        * ``detect_excludes`` references to rules that don't exist (silent typos
          would otherwise mean "exclude nothing").
        * Rules with no triggers — no detect_file*, detect_glob, or detect_dir —
          which can never match and are therefore dead config.
        """
        problems: list[str] = []
        names = set(self.disciplines)
        for name, rule in self.disciplines.items():
            for excl in rule.detect_excludes or ():
                if excl not in names:
                    problems.append(
                        f"section [{name}]: detect_excludes references unknown rule {excl!r}"
                    )
            has_trigger = bool(rule.detect_files) or bool(rule.detect_glob) or bool(rule.detect_dir)
            if not has_trigger:
                problems.append(
                    f"section [{name}]: has no triggers (detect_file*, detect_glob, or detect_dir)"
                )
        return problems

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

    def _has_required_files(self, repo: Path, rule: DisciplineRule) -> bool:
        """detect_requires_file is the only hard prerequisite — a gate on any trigger.

        Honors the same vendor/skip-dir set used by recursive subproject discovery
        so a vendored copy under ``node_modules`` / ``.venv`` / ``vendor`` doesn't
        satisfy the prereq and falsely classify the host repo.

        For recursive ``**/*.<ext>``-style patterns we walk the tree with
        ``os.walk`` and prune skip / hidden dirs *before* descending. The
        old implementation used ``Path.glob``, which scandirs every subtree
        before the in-loop filter could discard matches — on an Android
        repo with 88 subproject roots and ``build/`` + ``.gradle/`` under
        each, that turned a millisecond gate into an 85 s walk
        (~2 M scandir calls). Pruning at the directory level keeps the
        boolean answer identical while bringing cost back to milliseconds.
        Non-recursive patterns (e.g. ``lib/*.sh``) keep using ``Path.glob``;
        they don't descend into skip dirs in the first place.
        """
        pattern = rule.detect_requires_file
        if not pattern:
            return True
        if pattern.startswith("**/"):
            file_pat = pattern[len("**/") :]
            return self._has_pruned_recursive_match(repo, file_pat)
        return any(repo.glob(pattern))

    @staticmethod
    def _has_pruned_recursive_match(repo: Path, file_pat: str) -> bool:
        """Return True iff any file under *repo* matches *file_pat*, skipping
        vendor / cache / hidden directories at the directory level.
        """
        for _dirpath, dirnames, filenames in os.walk(repo):
            dirnames[:] = [
                d for d in dirnames
                if d not in _SUBPROJECT_SKIP_DIRS and not d.startswith(".")
            ]
            if any(fnmatchcase(f, file_pat) for f in filenames):
                return True
        return False

    def _any_detect_file_matches(self, repo: Path, rule: DisciplineRule) -> bool:
        for i, file_name in enumerate(rule.detect_files):
            path = repo / file_name
            if not path.exists():
                continue
            needle = rule.detect_contains[i] if i < len(rule.detect_contains) else ""
            if self._file_matches(path, needle):
                return True
        return False

    def _glob_or_dir_matches(self, repo: Path, rule: DisciplineRule) -> bool:
        if rule.detect_glob and any(repo.glob(rule.detect_glob)):
            return True
        return bool(rule.detect_dir and (repo / rule.detect_dir).is_dir())

    def _matches_rule(self, repo: Path, rule: DisciplineRule) -> bool:
        """A rule matches when its prerequisites hold and at least one trigger fires.

        Triggers are alternatives: any of detect_file(_alt|_alt2) (with optional
        content check), detect_glob, or detect_dir is enough. Glob-only or dir-only
        rules (e.g. frontend_nextjs's detect_glob=next.config.*) match correctly.
        """
        if not self._has_required_files(repo, rule):
            return False
        return self._any_detect_file_matches(repo, rule) or self._glob_or_dir_matches(repo, rule)

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

    def _manifest_basenames(self) -> tuple[frozenset[str], tuple[str, ...]]:
        """Return ``(filenames, globs)`` that mark a directory as a subproject root.

        Derived from the registry's own rules so it stays in sync with
        ``disciplines.conf``. Files referenced by a path (e.g. ``config/routes.rb``)
        are excluded — only top-level manifests count as roots.
        """
        files: set[str] = set()
        globs: list[str] = []
        for rule in self.disciplines.values():
            for f in rule.detect_files:
                if "/" not in f and "\\" not in f:
                    files.add(f)
            if rule.detect_glob:
                globs.append(rule.detect_glob)
        return frozenset(files), tuple(globs)

    def _is_subproject_root(self, dir_path: Path, files: frozenset[str], globs: tuple[str, ...]) -> bool:
        try:
            entries = {p.name for p in dir_path.iterdir() if p.is_file()}
        except OSError:
            return False
        if entries & files:
            return True
        return any(any(dir_path.glob(p)) for p in globs)

    def _iter_subproject_roots(self, repo: Path, max_depth: int) -> list[Path]:
        """BFS for directories that look like subproject roots, capped by depth.

        The repo root is always included first. Vendor/cache dirs and dotted dirs
        are pruned. The traversal continues into already-found roots so nested
        subprojects are still discoverable, but in practice ``max_depth`` keeps
        cost bounded.
        """
        files, globs = self._manifest_basenames()
        roots: list[Path] = [repo]
        queue: list[tuple[Path, int]] = [(repo, 0)]
        seen: set[Path] = {repo}
        while queue:
            current, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            try:
                children = list(current.iterdir())
            except OSError:
                continue
            for child in children:
                if not child.is_dir() or child in seen:
                    continue
                if child.name.startswith(".") or child.name in _SUBPROJECT_SKIP_DIRS:
                    continue
                seen.add(child)
                if self._is_subproject_root(child, files, globs):
                    roots.append(child)
                queue.append((child, depth + 1))
        return roots

    def detect_matches_recursive(
        self, repo: Path, max_depth: int = _DEFAULT_MAX_DEPTH,
    ) -> list[tuple[str, list[str]]]:
        """Walk *repo* finding subproject roots and return ``(rel_path, matches)`` per root.

        The repo root itself is always probed first. ``rel_path`` is ``"."`` for the
        root or the POSIX-style path relative to *repo* for nested subprojects.
        Roots with no matches are omitted from the result.
        """
        results: list[tuple[str, list[str]]] = []
        for root in self._iter_subproject_roots(repo, max_depth):
            matches = self.detect_matches(root)
            if not matches:
                continue
            rel = "." if root == repo else root.relative_to(repo).as_posix()
            results.append((rel, matches))
        return results
