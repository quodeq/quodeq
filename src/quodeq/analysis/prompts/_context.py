"""Prompt context dataclass and template placeholder constants."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quodeq.analysis.manifest import AnalysisTarget, SourceManifest

# Sentinel strings used when content is unavailable
NO_GUIDANCE = "_No additional guidance._"
NO_STANDARDS = "_No compiled standards available._"
NO_STANDARDS_FOR_DIM = "_No compiled standards for this dimension._"
STANDARDS_READ_ERROR = "_Could not read compiled standards._"

# Template placeholder names
TPL_DISCIPLINE = "DISCIPLINE"
TPL_REPO_NAME = "REPO_NAME"
TPL_DATE = "DATE"
TPL_DIMENSION = "DIMENSION"
TPL_SOURCE_FILE_COUNT = "SOURCE_FILE_COUNT"
TPL_STANDARDS_CHECKLIST = "STANDARDS_CHECKLIST"
TPL_ANALYSIS_GUIDANCE = "ANALYSIS_GUIDANCE"
TPL_DIMENSIONS = "DIMENSIONS"
TPL_PROMPT_HASH = "PROMPT_HASH"
TPL_SOURCE_MANIFEST = "SOURCE_MANIFEST"
TPL_DIMENSION_LIST = "DIMENSION_LIST"
TPL_STANDARDS_CHECKLISTS = "STANDARDS_CHECKLISTS"


@dataclass
class PromptContext:
    """Parameters for rendering a per-dimension analysis prompt."""

    language: str
    repo_name: str
    date_str: str
    dimension: str
    source_file_count: int
    dimensions_data: dict
    standards_dir: Path | None = None
    evaluators_dir: Path | None = None
    manifest: "SourceManifest | None" = None
    target: "AnalysisTarget | None" = None
    extra_vars: dict[str, str] = field(default_factory=dict)
    work_dir: Path | None = None


def render_manifest_context(context: PromptContext) -> str:
    """Render the source manifest context for the prompt.

    When a target is set, renders target-specific context (with other-module info).
    Otherwise falls back to the whole-repo manifest context.
    """
    if context.target is not None and context.manifest is not None:
        other_targets = [t for t in context.manifest.targets if t.name != context.target.name]
        return context.target.to_prompt_context(
            repo_total_files=context.manifest.total_files,
            other_targets=other_targets or None,
        )
    if context.manifest is not None:
        return context.manifest.to_prompt_context()
    return NO_GUIDANCE
