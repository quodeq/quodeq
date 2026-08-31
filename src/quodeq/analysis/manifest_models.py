"""Data models for the source manifest.

Prompt-text rendering lives in ``manifest_render`` (``describe_target``,
``render_target_prompt_context``, ``render_manifest_prompt_context``); the
entities here carry only data.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AnalysisTarget:
    """One analysis unit within a repository (e.g. 'rust_backend', 'dart_mobile').

    ``scope_path`` is the repo-relative directory the target lives in, or ``""`` for
    repo-root targets. In a monorepo, each subproject becomes its own target with
    its own scope_path; ``source_files`` paths are still expressed relative to the
    repo root regardless.
    """

    name: str
    language: str
    category: str | None = None
    frameworks: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    total_files: int = 0
    language_stats: dict[str, int] = field(default_factory=dict)
    scope_path: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("AnalysisTarget requires a name")
        if not self.language:
            raise ValueError("AnalysisTarget requires a language")


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
