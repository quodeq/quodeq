"""Prompt construction for subagent analysis."""
from __future__ import annotations

from quodeq.analysis.run_types import RunConfig, AnalysisContext
from quodeq.analysis.prompts.builder import build_analysis_prompt, prompt_context


def _build_subagent_prompt(
    config: RunConfig, dim_id: str, ctx: AnalysisContext,
    inline_findings: list[dict] | None = None,
) -> str:
    """Build the prompt for subagent analysis, optionally including previous findings."""
    return build_analysis_prompt(
        ctx.subagent_template, prompt_context(config, ctx, dim_id, inline_findings),
    )
