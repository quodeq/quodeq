"""Source manifest — rich prescan of a repository's source files."""
from __future__ import annotations

import logging
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# Re-export for backward compatibility (callers import from manifest)
from quodeq.analysis._detection import detect_language, list_source_files  # noqa: F401

_logger = logging.getLogger(__name__)

_MIN_FILES_PER_TARGET = 3


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
        """Render target as context for inclusion in analysis prompts.

        Intentionally co-located: the prompt context IS how the analysis
        target describes itself to the AI model — this is domain behavior,
        not user-facing presentation.
        """
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
