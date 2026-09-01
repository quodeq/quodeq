"""Multi-scope manifest building — partition a repo walk across subprojects.

Split out of ``manifest_build.py``: this module owns the deepest-scope
lookup and the single filesystem walk that buckets files by their owning
subproject, plus the manifest assembly that turns those buckets into one
target group per scope. The single-scope path (root-only or a pinned
``--scope``) stays in ``manifest_build.py``.
"""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from quodeq.analysis._ignore import is_ignored
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest
from quodeq.config.discipline_registry import DisciplineRegistry


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


def _walk_and_partition_by_scope(
    src: Path, ext_map: dict[str, str], skip_dirs: set[str],
    skip_patterns: list[str], scope_paths: list[str],
    ignore_patterns: list[str] | None = None,
) -> tuple[
    dict[str, dict[str, list[str]]],
    Counter[str],
    dict[str, dict[str, Counter]],
]:
    """Walk *src* once, bucketing files by their owning subproject scope.

    Each file is assigned to the deepest scope path that contains it. Files outside
    every scope are dropped — they don't belong to any classified subproject and
    shouldn't appear in any target. Callers that must not lose unclassified source
    pass ``"."`` among *scope_paths* as a catch-all (see _build_multi_scope_manifest).
    """
    from quodeq.analysis.manifest_build import (
        _UNKNOWN_LANG,
        _matches_skip_pattern,
        _prune_ignored_dirs,
    )

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
            if _matches_skip_pattern(rel, skip_patterns):
                continue
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


def _resolve_scope_paths(
    sub_results: list[tuple[str, list[str]]],
) -> tuple[list[str], dict[str, list]]:
    """Resolve scope_paths + matches_by_scope, ensuring a catch-all root scope.

    No rule classified the repo root, but source can still live outside every
    detected subproject — e.g. a Kotlin Multiplatform repo where only
    ``iosApp/`` matches (via *.xcodeproj) while the Gradle/Kotlin root does
    not. Without a catch-all root scope those files are dropped and the
    manifest comes back with no targets, which downstream reads as "no
    source files". "." is depth 0 in _deepest_scope, so it only claims files
    no more specific scope owns, and _MIN_FILES_PER_TARGET still keeps a
    handful of stray root files from becoming a target.
    """
    scope_paths = [rel for rel, _ in sub_results]
    matches_by_scope = {rel: matches for rel, matches in sub_results}
    if "." not in matches_by_scope:
        scope_paths.append(".")
        matches_by_scope["."] = []
    return scope_paths, matches_by_scope


def _build_scope_targets(
    scope_paths: list[str],
    matches_by_scope: dict[str, list],
    files_by_scope: dict[str, dict[str, list[str]]],
    ext_counts_by_scope_lang: dict[str, dict[str, Counter]],
    registry: DisciplineRegistry,
) -> list[AnalysisTarget]:
    """Build one AnalysisTarget group per scope from the partitioned files."""
    from quodeq.analysis.manifest_build import (
        _MIN_FILES_PER_TARGET,
        _build_targets_from_matches,
        target_name,
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
    return targets


def _build_multi_scope_manifest(
    src: Path,
    ext_map: dict[str, str],
    skip_dirs: set[str],
    skip_patterns: list[str],
    registry: DisciplineRegistry,
    sub_results: list[tuple[str, list[str]]],
    ignore_patterns: list[str] | None = None,
) -> SourceManifest:
    """Produce a manifest with one target group per detected subproject scope."""
    scope_paths, matches_by_scope = _resolve_scope_paths(sub_results)
    files_by_scope, ext_counts_overall, ext_counts_by_scope_lang = _walk_and_partition_by_scope(
        src, ext_map, skip_dirs, skip_patterns, scope_paths,
        ignore_patterns=ignore_patterns,
    )

    targets = _build_scope_targets(
        scope_paths, matches_by_scope, files_by_scope, ext_counts_by_scope_lang, registry,
    )

    targets.sort(key=lambda t: t.total_files, reverse=True)
    total = sum(t.total_files for t in targets)
    return SourceManifest(
        targets=targets, total_files=total, language_stats=dict(ext_counts_overall),
    )
