"""Leaf helpers shared by the single- and multi-scope manifest builders.

``manifest_build.py`` (single scope) and ``manifest_build_scope.py`` (one
target group per subproject) both need the same target naming, discipline
matching, and filtered repository walk; keeping them here means neither
builder imports the other.
"""
from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterator
from fnmatch import fnmatchcase
from pathlib import Path

from quodeq.analysis._ignore import is_ignored
from quodeq.analysis.manifest_models import AnalysisTarget, ManifestWalkSpec
from quodeq.config.discipline_registry import DisciplineRegistry

_MIN_FILES_PER_TARGET = 3
_UNKNOWN_LANG = "unknown"


def _matches_skip_pattern(rel_path: str, skip_patterns: list[str]) -> bool:
    """Return True when *rel_path* (POSIX, relative to the scan root) matches a
    skip_patterns glob from detection.json. fnmatch's ``*`` crosses directory
    separators, so ``*.min.js`` excludes matching files at any depth — the same
    semantics as .quodeqignore patterns.
    """
    return any(fnmatchcase(rel_path, pat) for pat in skip_patterns)


def target_name(language: str, category: str | None) -> str:
    """Build a filesystem-safe target name: '{language}_{category}' or bare '{language}'."""
    if category:
        return f"{language}_{category}"
    return language


def _build_targets_from_matches(
    registry: DisciplineRegistry,
    matches: list[str],
    files_by_lang: dict[str, list[str]],
    ext_counts_by_lang: dict[str, Counter],
    scope_path: str = "",
) -> list[AnalysisTarget]:
    """Construct AnalysisTargets from a precomputed match list, consuming languages."""
    targets: list[AnalysisTarget] = []
    claimed_languages: set[str] = set()
    for match_name in matches:
        rule = registry.disciplines.get(match_name)
        if rule is None or rule.language is None:
            continue
        lang = rule.language
        if lang in claimed_languages:
            continue
        lang_files = files_by_lang.get(lang, [])
        if len(lang_files) < _MIN_FILES_PER_TARGET:
            continue
        claimed_languages.add(lang)
        topics = list(rule.suggested_topics) if rule.suggested_topics else []
        ext_counts = ext_counts_by_lang.get(lang, Counter())
        targets.append(AnalysisTarget(
            name=target_name(lang, rule.category),
            language=lang,
            category=rule.category,
            frameworks=topics,
            source_files=sorted(lang_files),
            total_files=len(lang_files),
            language_stats=dict(ext_counts),
            scope_path=scope_path,
        ))

    for lang in claimed_languages:
        files_by_lang.pop(lang, None)
        ext_counts_by_lang.pop(lang, None)

    return targets


def _prune_ignored_dirs(
    src: Path, dirpath: str, dirnames: list[str], ignore_patterns: list[str],
) -> None:
    """Drop directories matching an ignore pattern so they are never descended."""
    dirnames[:] = [
        d for d in dirnames
        if not is_ignored(
            os.path.relpath(os.path.join(dirpath, d), src).replace(os.sep, "/"),
            ignore_patterns,
        )
    ]


def _iter_source_files(src: Path, walk_root: Path, walk: ManifestWalkSpec) -> Iterator[tuple[str, str, str]]:
    """Walk *walk_root* once, yielding ``(rel_path, suffix, language)`` per source file.

    Applies the walk spec's skip_dirs, skip_patterns and .quodeqignore
    patterns (anchored at *src*, not *walk_root*). Paths come back POSIX-style
    and relative to *src* so manifest paths are consistent across platforms —
    downstream consumers and scope-prefix matching all assume "/".
    """
    ext_map = walk.ext_map
    ignore_patterns = walk.ignore_patterns or []
    for dirpath, dirnames, filenames in os.walk(walk_root):
        dirnames[:] = [d for d in dirnames if d not in walk.skip_dirs and not d.startswith(".")]
        if ignore_patterns:
            _prune_ignored_dirs(src, dirpath, dirnames, ignore_patterns)
        for fname in filenames:
            suffix = os.path.splitext(fname)[1]
            if suffix not in ext_map:
                continue
            rel = os.path.relpath(os.path.join(dirpath, fname), src).replace(os.sep, "/")
            if _matches_skip_pattern(rel, walk.skip_patterns):
                continue
            if ignore_patterns and is_ignored(rel, ignore_patterns):
                continue
            yield rel, suffix, ext_map.get(suffix, _UNKNOWN_LANG)
