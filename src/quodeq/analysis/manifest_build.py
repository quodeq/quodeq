"""Manifest building — walk a repository and produce a SourceManifest."""
from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from quodeq.analysis._ignore import load_ignore_patterns
from quodeq.analysis.manifest_build_scope import _build_multi_scope_manifest
from quodeq.analysis.manifest_models import AnalysisTarget, ManifestWalkSpec, SourceManifest
from quodeq.analysis.manifest_targets import (
    _MIN_FILES_PER_TARGET,
    _build_targets_from_matches,
    _iter_source_files,
    target_name,
)
from quodeq.config.discipline_registry import DisciplineRegistry

_logger = logging.getLogger(__name__)


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


def _resolve_walk_root(src: Path, scope_path: str | None) -> Path:
    """The directory to walk: *src*, or the contained *scope_path* under it.

    Containment mirrors the CLI --scope guard (_cli_resolution): a scope that
    resolves outside the repo (traversal segments or a symlink) must not widen
    the walk; fall back to the full repo.
    """
    if not scope_path:
        return src
    candidate = src / scope_path
    if candidate.is_dir() and candidate.resolve().is_relative_to(src.resolve()):
        return candidate
    return src


def _walk_and_group(
    src: Path, walk: ManifestWalkSpec, scope_path: str | None = None,
) -> tuple[dict[str, list[str]], Counter[str], dict[str, Counter]]:
    """Walk *src* (or a scoped subdirectory) once, grouping files by language.

    When *scope_path* is given (relative to *src*), only files under that
    subdirectory are included.  Relative paths in the result are still
    expressed relative to *src* so callers see the same format regardless.
    *walk.ignore_patterns* (.quodeqignore) are anchored at *src*, not the scope.
    """
    files_by_lang: dict[str, list[str]] = {}
    ext_counts: Counter[str] = Counter()
    ext_counts_by_lang: dict[str, Counter] = {}
    for rel, suffix, lang in _iter_source_files(src, _resolve_walk_root(src, scope_path), walk):
        files_by_lang.setdefault(lang, []).append(rel)
        ext_counts[suffix] += 1
        ext_counts_by_lang.setdefault(lang, Counter())[suffix] += 1
    return files_by_lang, ext_counts, ext_counts_by_lang


def _build_single_scope_manifest(
    src: Path,
    walk: ManifestWalkSpec,
    disciplines_conf: Path | None,
    scope_path: str | None,
) -> SourceManifest:
    """Legacy single-scope path: walk once at the (optionally scoped) root."""
    files_by_lang, ext_counts, ext_counts_by_lang = _walk_and_group(
        src, walk, scope_path=scope_path,
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


def _resolve_registry_and_scopes(
    src: Path, disciplines_conf: Path | None,
) -> tuple[DisciplineRegistry | None, list[tuple[str, list[str]]] | None]:
    """Load the discipline registry (if any) and, when it classifies more
    than the repo root alone, its recursive subproject scopes.

    Returns ``(registry, sub_results)`` where *sub_results* is ``None`` when
    there is no registry, or when the registry classifies only a single
    root-level project — both cases mean the caller should take the legacy
    single-scope path.
    """
    registry: DisciplineRegistry | None = None
    if disciplines_conf and disciplines_conf.exists():
        try:
            registry = DisciplineRegistry.from_file(disciplines_conf)
        except (ValueError, OSError) as exc:
            _logger.warning("Discipline detection failed for %s: %s", disciplines_conf, exc)
            return None, None

    if registry is None:
        return None, None

    sub_results = registry.detect_matches_recursive(src)
    is_single_root = (
        not sub_results or (len(sub_results) == 1 and sub_results[0][0] == ".")
    )
    if is_single_root:
        return registry, None
    return registry, sub_results


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
    walk = ManifestWalkSpec(
        ext_map=detection.get("extensions", {}),
        skip_dirs=set(detection.get("skip_dirs", [])),
        skip_patterns=detection.get("skip_patterns", []),
        ignore_patterns=load_ignore_patterns(src),
    )

    if scope_path is not None:
        return _build_single_scope_manifest(src, walk, disciplines_conf, scope_path)

    registry, sub_results = _resolve_registry_and_scopes(src, disciplines_conf)
    if sub_results is not None:
        assert registry is not None  # sub_results is only set alongside a loaded registry
        return _build_multi_scope_manifest(src, walk, registry, sub_results)

    return _build_single_scope_manifest(src, walk, disciplines_conf, None)
