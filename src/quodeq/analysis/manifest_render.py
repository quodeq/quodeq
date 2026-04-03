"""Prompt-context rendering for AnalysisTarget — extracted from manifest.py."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quodeq.analysis.manifest_models import AnalysisTarget

_MAX_LANGUAGE_EXTENSIONS = 8


def render_target_prompt_context(
    target: AnalysisTarget,
    repo_total_files: int = 0,
    other_targets: list[AnalysisTarget] | None = None,
) -> str:
    """Render an AnalysisTarget as markdown context for inclusion in analysis prompts.

    Standalone function so the rendering concern is separate from the entity.
    """
    lines = [
        f"**Project type:** {target.project_description}",
        f"**Source files:** {target.total_files}"
        + (f" (of {repo_total_files} total in repo)" if repo_total_files > target.total_files else ""),
    ]
    if other_targets:
        others = ", ".join(
            f"{t.project_description} ({t.total_files} files)" for t in other_targets
        )
        lines.append(f"**Other modules:** {others}")
    if target.language_stats:
        breakdown = ", ".join(
            f"{ext}: {count}" for ext, count in
            sorted(target.language_stats.items(), key=lambda x: -x[1])[:_MAX_LANGUAGE_EXTENSIONS]
        )
        lines.append(f"**Extension breakdown:** {breakdown}")
    return "\n".join(lines)
