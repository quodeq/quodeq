"""Prompt construction for subagent analysis."""
from __future__ import annotations

from typing import Any

from quodeq.analysis._types import RunConfig
from quodeq.analysis.prompts.builder import PromptContext, build_analysis_prompt


def _build_subagent_prompt(
    config: RunConfig, dim_id: str, ctx: Any,
    inline_findings: list[dict] | None = None,
) -> str:
    """Build the prompt for subagent analysis, optionally including previous findings."""
    return build_analysis_prompt(
        ctx.subagent_template,
        PromptContext(
            language=config.language,
            repo_name=str(config.src),
            date_str=ctx.date_str,
            dimension=dim_id,
            source_file_count=config.source_file_count,
            dimensions_data=ctx.dimensions_data,
            standards_dir=config.standards_dir,
            evaluators_dir=config.evaluators_dir,
            manifest=config.manifest,
            target=config.target,
            work_dir=config.work_dir or config.src,
            previous_findings=inline_findings or [],
            project_root=config.src,
        ),
    )
