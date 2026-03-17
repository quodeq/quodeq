"""Source manifest — rich prescan of a repository's source files."""
from __future__ import annotations

import json
import logging
import os
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from quodeq.shared.utils import read_json

_logger = logging.getLogger(__name__)

_MIN_FILES_PER_TARGET = 3


def _walk_source_files(
    src: Path, extensions: set[str], skip_dirs: frozenset[str],
) -> Iterator[tuple[str, str]]:
    """Yield (relative_path, suffix) for source files, pruning skip dirs."""
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fname in filenames:
            suffix = os.path.splitext(fname)[1]
            if suffix in extensions:
                yield os.path.relpath(os.path.join(dirpath, fname), src), suffix


def list_source_files(src: Path, extensions: set[str], skip_dirs: frozenset[str] = frozenset()) -> list[str]:
    """List source files under *src* as paths relative to *src*."""
    files = [rel for rel, _ in _walk_source_files(src, extensions, skip_dirs)]
    files.sort()
    return files


def detect_language(src: Path, detection_file: Path) -> str:
    """Auto-detect the primary language for a repository using detection.json.

    Uses a two-pass approach:
    1. Check for config files at repo root (strong signal)
    2. Fall back to counting source files by extension (weak signal)
    """
    detection = read_json(detection_file)
    ext_map: dict[str, str] = detection.get("extensions", {})
    config_map: dict[str, str] = detection.get("config_files", {})
    skip_dirs = frozenset(detection.get("skip_dirs", []))

    # Pass 1: config files
    config_hits: Counter[str] = Counter()
    for config_file, lang in config_map.items():
        if (src / config_file).exists():
            config_hits[lang] += 1
    if config_hits:
        return config_hits.most_common(1)[0][0]

    # Pass 2: extension counts
    all_exts = set(ext_map.keys())
    lang_counts: Counter[str] = Counter()
    for _rel, suffix in _walk_source_files(src, all_exts, skip_dirs):
        lang = ext_map.get(suffix)
        if lang:
            lang_counts[lang] += 1
    if lang_counts:
        return lang_counts.most_common(1)[0][0]

    raise ValueError(f"No language detected in {src} using {detection_file}")


@dataclass
class AnalysisTarget:
    """One analysis unit within a repository (e.g. 'rust_backend', 'dart_mobile')."""

    name: str
    language: str
    category: str | None = None
    frameworks: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    total_files: int = 0
    language_stats: dict[str, int] = field(default_factory=dict)

    @property
    def project_description(self) -> str:
        """E.g. 'Kotlin mobile using Flutter'."""
        parts = [self.language.title()]
        if self.category:
            parts = [f"{self.language.title()} {self.category}"]
        if self.frameworks:
            parts.append(f"using {', '.join(self.frameworks)}")
        return " ".join(parts)

    def to_prompt_context(self, repo_total_files: int = 0, other_targets: list[AnalysisTarget] | None = None) -> str:
        """Render target as context for inclusion in analysis prompts."""
        lines = [
            f"**Project type:** {self.project_description}",
            f"**Source files:** {self.total_files}"
            + (f" (of {repo_total_files} total in repo)" if repo_total_files > self.total_files else ""),
        ]
        if other_targets:
            others = ", ".join(
                f"{t.project_description} ({t.total_files} files)" for t in other_targets
            )
            lines.append(f"**Other modules:** {others}")
        if self.language_stats:
            breakdown = ", ".join(
                f"{ext}: {count}" for ext, count in
                sorted(self.language_stats.items(), key=lambda x: -x[1])[:8]
            )
            lines.append(f"**Extension breakdown:** {breakdown}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize for JSON debugging output."""
        return {
            "name": self.name,
            "language": self.language,
            "category": self.category,
            "frameworks": self.frameworks,
            "project_description": self.project_description,
            "total_files": self.total_files,
            "source_files_count": len(self.source_files),
            "language_stats": self.language_stats,
        }


@dataclass
class SourceManifest:
    """Rich description of a repository's source structure."""

    targets: list[AnalysisTarget] = field(default_factory=list)
    total_files: int = 0
    language_stats: dict[str, int] = field(default_factory=dict)

    # --- backward-compat properties (delegate to primary target) ---

    @property
    def _primary(self) -> AnalysisTarget | None:
        """Primary target = largest by file count."""
        if not self.targets:
            return None
        return max(self.targets, key=lambda t: t.total_files)

    @property
    def language(self) -> str:
        p = self._primary
        return p.language if p else "unknown"

    @property
    def category(self) -> str | None:
        p = self._primary
        return p.category if p else None

    @property
    def frameworks(self) -> list[str]:
        p = self._primary
        return p.frameworks if p else []

    @property
    def source_files(self) -> list[str]:
        """All source files across all targets (backward compat)."""
        if not self.targets:
            return []
        if len(self.targets) == 1:
            return self.targets[0].source_files
        merged: list[str] = []
        for t in self.targets:
            merged.extend(t.source_files)
        merged.sort()
        return merged

    @property
    def project_description(self) -> str:
        p = self._primary
        return p.project_description if p else "Unknown"

    def to_prompt_context(self) -> str:
        """Render manifest as context for inclusion in analysis prompts."""
        if not self.targets:
            lines = [
                "**Project type:** Unknown",
                f"**Source files:** {self.total_files}",
            ]
            if self.language_stats:
                breakdown = ", ".join(
                    f"{ext}: {count}" for ext, count in
                    sorted(self.language_stats.items(), key=lambda x: -x[1])[:8]
                )
                lines.append(f"**Extension breakdown:** {breakdown}")
            return "\n".join(lines)

        if len(self.targets) == 1:
            return self.targets[0].to_prompt_context(repo_total_files=self.total_files)

        # Multi-language: describe all detected modules
        lines = [f"**Source files:** {self.total_files}"]
        lines.append("**Detected modules:**")
        for t in self.targets:
            lines.append(f"- {t.project_description} ({t.total_files} files)")
        lines.append("")
        lines.append("Analyze each file according to its language and project type.")
        if self.language_stats:
            breakdown = ", ".join(
                f"{ext}: {count}" for ext, count in
                sorted(self.language_stats.items(), key=lambda x: -x[1])[:8]
            )
            lines.append(f"**Extension breakdown:** {breakdown}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize for JSON debugging output."""
        return {
            "language": self.language,
            "category": self.category,
            "frameworks": self.frameworks,
            "project_description": self.project_description,
            "total_files": self.total_files,
            "source_files_count": len(self.source_files),
            "language_stats": self.language_stats,
            "targets": [t.to_dict() for t in self.targets],
        }


def _target_name(language: str, category: str | None) -> str:
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
    except (ValueError, OSError):
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
            name=_target_name(lang, rule.category),
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
    all_extensions = set(ext_map.keys())

    # Single walk: collect all source files grouped by language
    files_by_lang: dict[str, list[str]] = {}
    ext_counts: Counter[str] = Counter()
    ext_counts_by_lang: dict[str, Counter] = {}
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

    all_source_files_count = sum(len(f) for f in files_by_lang.values())

    # Build targets from discipline matches (mutates files_by_lang, claiming matched langs)
    targets: list[AnalysisTarget] = []
    if disciplines_conf and disciplines_conf.exists():
        targets = _build_targets_from_disciplines(
            src, disciplines_conf, files_by_lang, ext_counts_by_lang,
        )

    # Remaining languages with no discipline match → bare targets
    for lang, lang_files in files_by_lang.items():
        if len(lang_files) < _MIN_FILES_PER_TARGET:
            continue
        lang_ext_counts = ext_counts_by_lang.get(lang, Counter())
        targets.append(AnalysisTarget(
            name=_target_name(lang, None),
            language=lang,
            source_files=sorted(lang_files),
            total_files=len(lang_files),
            language_stats=dict(lang_ext_counts),
        ))

    # Sort targets: largest first (primary target)
    targets.sort(key=lambda t: t.total_files, reverse=True)

    return SourceManifest(
        targets=targets,
        total_files=all_source_files_count,
        language_stats=dict(ext_counts),
    )


def _detect_category(
    src: Path, disciplines_conf: Path,
) -> tuple[str | None, list[str]]:
    """Use DisciplineRegistry to detect category and suggested topics."""
    try:
        from quodeq.config.discipline_registry import DisciplineRegistry

        registry = DisciplineRegistry.from_file(disciplines_conf)
        matches = registry.detect_matches(src)
        if not matches:
            return None, []
        best = registry.choose_highest_priority(matches)
        rule = registry.disciplines.get(best)
        if rule is None:
            return None, []
        topics = list(rule.suggested_topics) if rule.suggested_topics else []
        return rule.category, topics
    except (ValueError, OSError):
        return None, []
