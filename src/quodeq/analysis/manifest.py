"""Source manifest — rich prescan of a repository's source files."""
from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from quodeq.shared.utils import read_json


@dataclass
class SourceManifest:
    """Rich description of a repository's source structure."""

    language: str
    category: str | None = None
    frameworks: list[str] = field(default_factory=list)
    total_files: int = 0
    source_files: list[str] = field(default_factory=list)
    language_stats: dict[str, int] = field(default_factory=dict)

    def to_prompt_context(self) -> str:
        """Render manifest as context for inclusion in analysis prompts."""
        lines = [
            f"**Primary language:** {self.language}",
            f"**Source files:** {self.total_files}",
        ]
        if self.category:
            lines.append(f"**Category:** {self.category}")
        if self.frameworks:
            lines.append(f"**Frameworks / topics:** {', '.join(self.frameworks)}")
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
            "total_files": self.total_files,
            "source_files_count": len(self.source_files),
            "language_stats": self.language_stats,
        }


def _load_detection_config(detection_file: Path) -> dict:
    """Load detection.json, returning its parsed content."""
    return read_json(detection_file)


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

    # Single walk: collect all source files and count by extension
    source_files: list[str] = []
    ext_counts: Counter[str] = Counter()
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fname in filenames:
            suffix = os.path.splitext(fname)[1]
            if suffix in all_extensions:
                rel = os.path.relpath(os.path.join(dirpath, fname), src)
                source_files.append(rel)
                ext_counts[suffix] += 1

    source_files.sort()

    # Determine primary language by file count
    lang_counts: Counter[str] = Counter()
    for ext, count in ext_counts.items():
        lang = ext_map.get(ext, "unknown")
        lang_counts[lang] += count

    primary_language = lang_counts.most_common(1)[0][0] if lang_counts else "unknown"

    # Detect category and frameworks from disciplines.conf
    category: str | None = None
    frameworks: list[str] = []
    if disciplines_conf and disciplines_conf.exists():
        category, frameworks = _detect_category(src, disciplines_conf)

    return SourceManifest(
        language=primary_language,
        category=category,
        frameworks=frameworks,
        total_files=len(source_files),
        source_files=source_files,
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
