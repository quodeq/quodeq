"""Data models for the source manifest."""
from __future__ import annotations

from dataclasses import dataclass, field

from quodeq.analysis.manifest_render import render_target_prompt_context

_MAX_EXTENSION_DISPLAY = 8


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

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("AnalysisTarget requires a name")
        if not self.language:
            raise ValueError("AnalysisTarget requires a language")

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

        Delegates to :func:`render_target_prompt_context`.
        """
        return render_target_prompt_context(self, repo_total_files, other_targets)

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

    def add_target(self, target: AnalysisTarget) -> None:
        """Add an analysis target to this manifest."""
        self.targets.append(target)
        self.total_files = sum(t.total_files for t in self.targets)

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
                    sorted(self.language_stats.items(), key=lambda x: -x[1])[:_MAX_EXTENSION_DISPLAY]
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
                sorted(self.language_stats.items(), key=lambda x: -x[1])[:_MAX_EXTENSION_DISPLAY]
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
