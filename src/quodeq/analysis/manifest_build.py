"""Manifest building — walk a repository and produce a SourceManifest."""
from __future__ import annotations

import logging
import os
from collections import Counter
from pathlib import Path

from quodeq.analysis._ignore import is_ignored, load_ignore_patterns
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest
from quodeq.config.discipline_registry import DisciplineRegistry

_logger = logging.getLogger(__name__)

_MIN_FILES_PER_TARGET = 3
_UNKNOWN_LANG = "unknown"


def _deepest_scope(rel_path: str, scope_paths: list[str]) -> str | None:
    """Return the most-specific scope (by path depth) that contains *rel_path*.

    Used when partitioning files across subprojects in a monorepo. ``"."`` matches
    any file as a fallback. Returns ``None`` only when *scope_paths* is empty or
    contains no scope that covers the file (i.e. no ``"."`` and no ancestor scope).
    """
    best: str | None = None
    best_depth = -1
    for scope in scope_paths:
        if scope == ".":
            depth = 0
        else:
            prefix = scope + "/"
            if rel_path != scope and not rel_path.startswith(prefix):
                continue
            depth = scope.count("/") + 1
        if depth > best_depth:
            best = scope
            best_depth = depth
    return best


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


def _build_targets_from_disciplines(
    src: Path, disciplines_conf: Path,
    files_by_lang: dict[str, list[str]], ext_counts_by_lang: dict[str, Counter],
) -> list[AnalysisTarget]:
    """Build AnalysisTarget list for a single-scope walk via root-level detection."""
    try:
        registry = DisciplineRegistry.from_file(disciplines_conf)
        matches = registry.detect_matches(src)
    except (ValueError, OSError) as exc:
        _logger.warning("Discipline detection failed for %s: %s", disciplines_conf, exc)
        return []
    return _build_targets_from_matches(registry, matches, files_by_lang, ext_counts_by_lang)


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


def _walk_and_group(
    src: Path, ext_map: dict[str, str], skip_dirs: set[str],
    scope_path: str | None = None,
    ignore_patterns: list[str] | None = None,
) -> tuple[dict[str, list[str]], Counter[str], dict[str, Counter]]:
    """Walk *src* (or a scoped subdirectory) once, grouping files by language.

    When *scope_path* is given (relative to *src*), only files under that
    subdirectory are included.  Relative paths in the result are still
    expressed relative to *src* so callers see the same format regardless.
    *ignore_patterns* (.quodeqignore) are anchored at *src*, not the scope.
    """
    walk_root = src
    if scope_path:
        candidate = src / scope_path
        if candidate.is_dir():
            walk_root = candidate

    ignore_patterns = ignore_patterns or []
    files_by_lang: dict[str, list[str]] = {}
    ext_counts: Counter[str] = Counter()
    ext_counts_by_lang: dict[str, Counter] = {}
    all_extensions = set(ext_map.keys())
    for dirpath, dirnames, filenames in os.walk(walk_root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
        if ignore_patterns:
            _prune_ignored_dirs(src, dirpath, dirnames, ignore_patterns)
        for fname in filenames:
            suffix = os.path.splitext(fname)[1]
            if suffix in all_extensions:
                # Normalize to POSIX separators so manifest paths are consistent
                # across platforms — downstream consumers and scope-prefix
                # matching all assume "/".
                rel = os.path.relpath(os.path.join(dirpath, fname), src).replace(os.sep, "/")
                if ignore_patterns and is_ignored(rel, ignore_patterns):
                    continue
                lang = ext_map.get(suffix, _UNKNOWN_LANG)
                files_by_lang.setdefault(lang, []).append(rel)
                ext_counts[suffix] += 1
                ext_counts_by_lang.setdefault(lang, Counter())[suffix] += 1
    return files_by_lang, ext_counts, ext_counts_by_lang


def _walk_and_partition_by_scope(
    src: Path, ext_map: dict[str, str], skip_dirs: set[str], scope_paths: list[str],
    ignore_patterns: list[str] | None = None,
) -> tuple[
    dict[str, dict[str, list[str]]],
    Counter[str],
    dict[str, dict[str, Counter]],
]:
    """Walk *src* once, bucketing files by their owning subproject scope.

    Each file is assigned to the deepest scope path that contains it. Files outside
    every scope are silently dropped — they don't belong to any classified
    subproject and shouldn't appear in any target.
    """
    ignore_patterns = ignore_patterns or []
    files_by_scope_lang: dict[str, dict[str, list[str]]] = {s: {} for s in scope_paths}
    ext_counts_overall: Counter[str] = Counter()
    ext_counts_by_scope_lang: dict[str, dict[str, Counter]] = {s: {} for s in scope_paths}
    all_extensions = set(ext_map.keys())
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
        if ignore_patterns:
            _prune_ignored_dirs(src, dirpath, dirnames, ignore_patterns)
        for fname in filenames:
            suffix = os.path.splitext(fname)[1]
            if suffix not in all_extensions:
                continue
            # Match the POSIX-style scope_paths from detect_matches_recursive
            # so prefix matching works on Windows.
            rel = os.path.relpath(os.path.join(dirpath, fname), src).replace(os.sep, "/")
            if ignore_patterns and is_ignored(rel, ignore_patterns):
                continue
            owner = _deepest_scope(rel, scope_paths)
            if owner is None:
                continue
            lang = ext_map.get(suffix, _UNKNOWN_LANG)
            files_by_scope_lang[owner].setdefault(lang, []).append(rel)
            ext_counts_overall[suffix] += 1
            ext_counts_by_scope_lang[owner].setdefault(lang, Counter())[suffix] += 1
    return files_by_scope_lang, ext_counts_overall, ext_counts_by_scope_lang


def _build_multi_scope_manifest(
    src: Path,
    ext_map: dict[str, str],
    skip_dirs: set[str],
    registry: DisciplineRegistry,
    sub_results: list[tuple[str, list[str]]],
    ignore_patterns: list[str] | None = None,
) -> SourceManifest:
    """Produce a manifest with one target group per detected subproject scope."""
    scope_paths = [rel for rel, _ in sub_results]
    matches_by_scope = {rel: matches for rel, matches in sub_results}
    files_by_scope, ext_counts_overall, ext_counts_by_scope_lang = _walk_and_partition_by_scope(
        src, ext_map, skip_dirs, scope_paths, ignore_patterns=ignore_patterns,
    )

    targets: list[AnalysisTarget] = []
    for scope in scope_paths:
        lang_files = files_by_scope[scope]
        ext_counts_by_lang = ext_counts_by_scope_lang[scope]
        framework_targets = _build_targets_from_matches(
            registry, matches_by_scope[scope], lang_files, ext_counts_by_lang,
            scope_path=scope,
        )
        targets.extend(framework_targets)
        for lang, files in lang_files.items():
            if len(files) < _MIN_FILES_PER_TARGET:
                continue
            targets.append(AnalysisTarget(
                name=target_name(lang, None),
                language=lang,
                source_files=sorted(files),
                total_files=len(files),
                language_stats=dict(ext_counts_by_lang.get(lang, Counter())),
                scope_path=scope,
            ))

    targets.sort(key=lambda t: t.total_files, reverse=True)
    total = sum(t.total_files for t in targets)
    return SourceManifest(
        targets=targets, total_files=total, language_stats=dict(ext_counts_overall),
    )


def _build_single_scope_manifest(
    src: Path,
    ext_map: dict[str, str],
    skip_dirs: set[str],
    disciplines_conf: Path | None,
    scope_path: str | None,
    ignore_patterns: list[str] | None = None,
) -> SourceManifest:
    """Legacy single-scope path: walk once at the (optionally scoped) root."""
    files_by_lang, ext_counts, ext_counts_by_lang = _walk_and_group(
        src, ext_map, skip_dirs, scope_path=scope_path, ignore_patterns=ignore_patterns,
    )
    all_source_files_count = sum(len(f) for f in files_by_lang.values())

    scope_label = scope_path or ""
    targets: list[AnalysisTarget] = []
    if disciplines_conf and disciplines_conf.exists():
        targets = _build_targets_from_disciplines(
            src, disciplines_conf, files_by_lang, ext_counts_by_lang,
        )
        for t in targets:
            t.scope_path = scope_label
    for lang, lang_files in files_by_lang.items():
        if len(lang_files) < _MIN_FILES_PER_TARGET:
            continue
        lang_ext_counts = ext_counts_by_lang.get(lang, Counter())
        targets.append(AnalysisTarget(
            name=target_name(lang, None),
            language=lang,
            source_files=sorted(lang_files),
            total_files=len(lang_files),
            language_stats=dict(lang_ext_counts),
            scope_path=scope_label,
        ))
    targets.sort(key=lambda t: t.total_files, reverse=True)

    return SourceManifest(
        targets=targets,
        total_files=all_source_files_count,
        language_stats=dict(ext_counts),
    )


def build_manifest(
    src: Path,
    detection: dict,
    disciplines_conf: Path | None = None,
    scope_path: str | None = None,
) -> SourceManifest:
    """Walk a repository and build a SourceManifest.

    When *scope_path* is provided the caller has pinned analysis to a single
    subdirectory and we behave classically: one walk, one set of targets.

    Otherwise, recursive subproject discovery runs first. If multiple subproject
    roots are found (or any root other than the repo itself), the manifest is
    built per-scope: each subproject gets its own targets with framework-aware
    classification, and files are partitioned to the deepest enclosing scope.
    Repos with a single root-level project (or no detected subprojects) take
    the legacy single-scope path so existing behaviour is preserved.

    *detection* is the parsed content of detection.json. *disciplines_conf* is
    optional; without it, no discipline-based classification runs.

    A ``.quodeqignore`` file at *src* adds repo-local exclusions on top of the
    built-in skip_dirs (see quodeq.analysis._ignore for the pattern syntax).
    """
    ext_map: dict[str, str] = detection.get("extensions", {})
    skip_dirs = set(detection.get("skip_dirs", []))
    ignore_patterns = load_ignore_patterns(src)

    if scope_path is not None:
        return _build_single_scope_manifest(
            src, ext_map, skip_dirs, disciplines_conf, scope_path,
            ignore_patterns=ignore_patterns,
        )

    registry: DisciplineRegistry | None = None
    if disciplines_conf and disciplines_conf.exists():
        try:
            registry = DisciplineRegistry.from_file(disciplines_conf)
        except (ValueError, OSError) as exc:
            _logger.warning("Discipline detection failed for %s: %s", disciplines_conf, exc)

    if registry is not None:
        sub_results = registry.detect_matches_recursive(src)
        is_single_root = (
            not sub_results or (len(sub_results) == 1 and sub_results[0][0] == ".")
        )
        if not is_single_root:
            return _build_multi_scope_manifest(
                src, ext_map, skip_dirs, registry, sub_results,
                ignore_patterns=ignore_patterns,
            )

    return _build_single_scope_manifest(
        src, ext_map, skip_dirs, disciplines_conf, None,
        ignore_patterns=ignore_patterns,
    )
