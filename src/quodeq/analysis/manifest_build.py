"""Manifest building — walk a repository and produce a SourceManifest."""
from __future__ import annotations

import logging
import os
from collections import Counter
from pathlib import Path

from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest

_logger = logging.getLogger(__name__)

_MIN_FILES_PER_TARGET = 3


def target_name(language: str, category: str | None) -> str:
    """Build a filesystem-safe target name: '{language}_{category}' or bare '{language}'."""
    if category:
        return f"{language}_{category}"
    return language


def _build_targets_from_disciplines(
    src: Path, disciplines_conf: Path,
    files_by_lang: dict[str, list[str]], ext_counts_by_lang: dict[str, Counter],
) -> list[AnalysisTarget]:
    """Build AnalysisTarget list using discipline matching, consuming matched languages."""
    try:
        from quodeq.config.discipline_registry import DisciplineRegistry

        registry = DisciplineRegistry.from_file(disciplines_conf)
        matches = registry.detect_matches(src)
    except (ValueError, OSError) as exc:
        _logger.warning("Discipline detection failed for %s: %s", disciplines_conf, exc)
        return []

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
        ))

    # Remove claimed languages from the dicts so callers can process leftovers
    for lang in claimed_languages:
        files_by_lang.pop(lang, None)
        ext_counts_by_lang.pop(lang, None)

    return targets


def _walk_and_group(
    src: Path, ext_map: dict[str, str], skip_dirs: set[str],
) -> tuple[dict[str, list[str]], Counter[str], dict[str, Counter]]:
    """Walk *src* once, grouping files by language."""
    files_by_lang: dict[str, list[str]] = {}
    ext_counts: Counter[str] = Counter()
    ext_counts_by_lang: dict[str, Counter] = {}
    all_extensions = set(ext_map.keys())
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fname in filenames:
            suffix = os.path.splitext(fname)[1]
            if suffix in all_extensions:
                rel = os.path.relpath(os.path.join(dirpath, fname), src)
                lang = ext_map.get(suffix, "unknown")
                files_by_lang.setdefault(lang, []).append(rel)
                ext_counts[suffix] += 1
                ext_counts_by_lang.setdefault(lang, Counter())[suffix] += 1
    return files_by_lang, ext_counts, ext_counts_by_lang


def build_manifest(
    src: Path,
    detection: dict,
    disciplines_conf: Path | None = None,
) -> SourceManifest:
    """Walk a repository once and build a complete source manifest.

    *detection* is the parsed content of detection.json.
    *disciplines_conf* is the optional path to disciplines.conf for
    category and framework detection.
    """
    ext_map: dict[str, str] = detection.get("extensions", {})
    skip_dirs = set(detection.get("skip_dirs", []))
    files_by_lang, ext_counts, ext_counts_by_lang = _walk_and_group(src, ext_map, skip_dirs)
    all_source_files_count = sum(len(f) for f in files_by_lang.values())

    targets: list[AnalysisTarget] = []
    if disciplines_conf and disciplines_conf.exists():
        targets = _build_targets_from_disciplines(
            src, disciplines_conf, files_by_lang, ext_counts_by_lang,
        )
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
        ))
    targets.sort(key=lambda t: t.total_files, reverse=True)

    return SourceManifest(
        targets=targets,
        total_files=all_source_files_count,
        language_stats=dict(ext_counts),
    )
