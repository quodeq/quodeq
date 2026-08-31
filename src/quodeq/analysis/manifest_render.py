"""Prompt-context rendering for AnalysisTarget / SourceManifest — extracted
from manifest_models.py so the entities stay free of rendering concerns.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest

# Shared by both renderers below (was duplicated as
# manifest_models._MAX_EXTENSION_DISPLAY, same value).
_MAX_LANGUAGE_EXTENSIONS = 8


def describe_target(target: AnalysisTarget) -> str:
    """E.g. 'Kotlin mobile using Flutter'."""
    parts = [target.language.title()]
    if target.category:
        parts = [f"{target.language.title()} {target.category}"]
    if target.frameworks:
        parts.append(f"using {', '.join(target.frameworks)}")
    return " ".join(parts)


def render_target_prompt_context(
    target: AnalysisTarget,
    repo_total_files: int = 0,
    other_targets: list[AnalysisTarget] | None = None,
) -> str:
    """Render an AnalysisTarget as markdown context for inclusion in analysis prompts.

    Standalone function so the rendering concern is separate from the entity.
    """
    lines = [
        f"**Project type:** {describe_target(target)}",
        f"**Source files:** {target.total_files}"
        + (f" (of {repo_total_files} total in repo)" if repo_total_files > target.total_files else ""),
    ]
    if other_targets:
        others = ", ".join(
            f"{describe_target(t)} ({t.total_files} files)" for t in other_targets
        )
        lines.append(f"**Other modules:** {others}")
    if target.language_stats:
        breakdown = ", ".join(
            f"{ext}: {count}" for ext, count in
            sorted(target.language_stats.items(), key=lambda x: -x[1])[:_MAX_LANGUAGE_EXTENSIONS]
        )
        lines.append(f"**Extension breakdown:** {breakdown}")
    return "\n".join(lines)


def _render_no_targets(manifest: SourceManifest) -> str:
    lines = [
        "**Project type:** Unknown",
        f"**Source files:** {manifest.total_files}",
    ]
    if manifest.language_stats:
        breakdown = ", ".join(
            f"{ext}: {count}" for ext, count in
            sorted(manifest.language_stats.items(), key=lambda x: -x[1])[:_MAX_LANGUAGE_EXTENSIONS]
        )
        lines.append(f"**Extension breakdown:** {breakdown}")
    return "\n".join(lines)


def _render_multi_target(manifest: SourceManifest) -> str:
    lines = [f"**Source files:** {manifest.total_files}"]
    lines.append("**Detected modules:**")
    for t in manifest.targets:
        lines.append(f"- {describe_target(t)} ({t.total_files} files)")
    lines.append("")
    lines.append("Analyze each file according to its language and project type.")
    if manifest.language_stats:
        breakdown = ", ".join(
            f"{ext}: {count}" for ext, count in
            sorted(manifest.language_stats.items(), key=lambda x: -x[1])[:_MAX_LANGUAGE_EXTENSIONS]
        )
        lines.append(f"**Extension breakdown:** {breakdown}")
    return "\n".join(lines)


def render_manifest_prompt_context(manifest: SourceManifest) -> str:
    """Render a SourceManifest as markdown context for inclusion in analysis prompts.

    Standalone function so the rendering concern is separate from the entity.
    Three shapes, in order of precedence: no targets (unknown project type),
    a single target (delegates to render_target_prompt_context), or multiple
    targets (a "detected modules" summary of each).
    """
    if not manifest.targets:
        return _render_no_targets(manifest)
    if len(manifest.targets) == 1:
        return render_target_prompt_context(manifest.targets[0], manifest.total_files, None)
    return _render_multi_target(manifest)
