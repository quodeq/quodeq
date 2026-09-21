"""Prompt builder — assembles per-dimension analysis prompts from compass.md template."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from quodeq.analysis.prompts import _context as ctx
from quodeq.data.fs.standards_prefs import load_project_overrides
from quodeq.analysis.prompts._renderers import (
    _load_dimension_data,
    render_compiled_standards,
    render_compact_standards,
    render_dimensions,
)
from quodeq.analysis.prompts._standards_io import (
    render_all_standards,
    write_standards_and_instruction,
)
from quodeq.analysis.prompts.template import load_template, template_hash
from quodeq.config.prompt_templates import render_template

if TYPE_CHECKING:
    from quodeq.analysis.run_types import AnalysisContext, RunConfig

_logger = logging.getLogger(__name__)

_TPL_EVALUATION_RULES = "EVALUATION_RULES"


def load_evaluation_rules() -> str:
    """Load shared evaluation rules + reporting format.

    Concatenates two prompt files into the same template slot. They are
    kept apart on disk so the incremental cache can treat them
    differently:

    - evaluation_rules.md is rules-bearing (in ``_RULES_BEARING_PROMPTS``)
      — anything that decides what counts as a violation. Edits force a
      full re-analysis.
    - finding_format.md is reporting/quoting/phrasing discipline. Edits
      do NOT invalidate carry-forward.
    """
    parts: list[str] = []
    for name in ("evaluation_rules.md", "finding_format.md"):
        try:
            parts.append(load_template(template_name=name))
        except OSError:
            _logger.warning("Failed to load prompt template %s, skipping", name)
            continue
    return "\n\n".join(p for p in parts if p)


def render_previous_findings_section(findings: list[dict]) -> str:
    """Render a prompt section listing previous findings grouped by file."""
    if not findings:
        return ""

    grouped: dict[str, list[dict]] = {}
    for f in findings:
        key = f.get("file", "(unknown file)")
        grouped.setdefault(key, []).append(f)

    lines = [
        "",
        "## Previous findings for files in this batch",
        "",
        "The following findings were reported in a prior evaluation. For each file",
        "you analyze, confirm whether these findings still apply to the current code.",
        "Report confirmed findings alongside any new ones you discover.",
        "Dismiss findings that no longer apply by not reporting them.",
        "",
    ]
    for filepath, file_findings in sorted(grouped.items()):
        lines.append(f"### {filepath}")
        for f in file_findings:
            ftype = f.get("t", "finding")
            req = f.get("req", "")
            line_num = f.get("line", "?")
            reason = f.get("reason", "")
            lines.append(f"- [{ftype}] {req} line {line_num}: {reason}")
        lines.append("")

    return "\n".join(lines)


# Re-export public API so existing ``from ...builder import X`` keeps working
PromptContext = ctx.PromptContext
__all__ = [
    "PromptContext",
    "prompt_context",
    "build_analysis_prompt",
    "build_consolidated_prompt",
    "load_template",
    "render_compiled_standards",
    "render_dimensions",
    "render_previous_findings_section",
    "_load_dimension_data",
]


def _resolve_standards_checklist(context: ctx.PromptContext) -> str:
    """Render the standards checklist for *context*, or the no-standards marker.

    With a work dir the compact rendering is written to disk and replaced by
    a read instruction; without one the full compiled rendering is inlined.
    """
    if not context.standards_dir:
        return ctx.NO_STANDARDS
    compiled_dir = context.standards_dir / "compiled"
    eval_dir = context.evaluators_dir
    overrides = load_project_overrides(context.project_root)
    if not (compiled_dir.exists() or (eval_dir and eval_dir.is_dir())):
        return ctx.NO_STANDARDS
    if not context.work_dir:
        return render_compiled_standards(
            compiled_dir, context.dimension, evaluators_dir=eval_dir, overrides=overrides,
        )
    compact = render_compact_standards(
        compiled_dir, context.dimension, evaluators_dir=eval_dir, overrides=overrides,
    )
    if compact == ctx.NO_STANDARDS_FOR_DIM:
        return compact
    return write_standards_and_instruction(context.work_dir, context.dimension, compact)


def _shared_values(context: ctx.PromptContext, manifest_context: str, prompt_hash: str) -> dict[str, str]:
    """The template values both prompt shapes fill identically.

    Each builder adds the slots only it has (the single dimension and its
    checklist, or the dimension list and all checklists) on top.
    """
    return {
        ctx.TPL_DISCIPLINE: context.language,
        ctx.TPL_REPO_NAME: context.repo_name,
        ctx.TPL_DATE: context.date_str,
        ctx.TPL_SOURCE_FILE_COUNT: str(context.source_file_count),
        ctx.TPL_ANALYSIS_GUIDANCE: manifest_context,
        ctx.TPL_PROMPT_HASH: prompt_hash,
        ctx.TPL_SOURCE_MANIFEST: manifest_context,
        _TPL_EVALUATION_RULES: load_evaluation_rules(),
    }


def _render(template: str, context: ctx.PromptContext, values: dict[str, str]) -> str:
    """Render *template* with *values*, letting the context's extra vars win."""
    if context.extra_vars:
        values.update(context.extra_vars)
    return render_template(template, values)


def prompt_context(
    config: "RunConfig", run_ctx: "AnalysisContext", dimension: str,
    previous_findings: list[dict] | None = None,
) -> ctx.PromptContext:
    """The PromptContext an analysis prompt for *dimension* is built from.

    One reading of the run config and context, shared by the per-dimension,
    subagent and consolidated prompt builders. *previous_findings* is the
    inline findings block only the subagent prompt carries.
    """
    return ctx.PromptContext(
        language=config.language,
        repo_name=str(config.src),
        date_str=run_ctx.date_str,
        dimension=dimension,
        source_file_count=config.source_file_count,
        dimensions_data=run_ctx.dimensions_data,
        standards_dir=config.standards_dir,
        evaluators_dir=config.evaluators_dir,
        manifest=config.manifest,
        target=config.target,
        work_dir=config.work_dir or config.src,
        previous_findings=previous_findings or [],
        project_root=config.src,
    )


def build_analysis_prompt(template: str, context: ctx.PromptContext) -> str:
    """Build a complete per-dimension analysis prompt from the template."""
    dimensions_text = render_dimensions(context.dimensions_data, context.dimension)
    prompt_hash = template_hash(template)
    standards_checklist = _resolve_standards_checklist(context)

    manifest_context = ctx.render_manifest_context(context)
    values = _shared_values(context, manifest_context, prompt_hash)
    values[ctx.TPL_DIMENSION] = context.dimension
    values[ctx.TPL_STANDARDS_CHECKLIST] = standards_checklist
    values[ctx.TPL_DIMENSIONS] = dimensions_text
    result = _render(template, context, values)
    prev_section = render_previous_findings_section(context.previous_findings)
    if prev_section:
        result += prev_section
    return result


def build_consolidated_prompt(
    dimensions: list[str],
    context: ctx.PromptContext,
    template: str | None = None,
) -> str:
    """Build a multi-dimension analysis prompt with all standards inline."""
    if template is None:
        template = load_template(template_name="cli_consolidated_prompt.md")

    standards_text = render_all_standards(
        context.standards_dir, dimensions, evaluators_dir=context.evaluators_dir,
        overrides=load_project_overrides(context.project_root),
    ) if context.standards_dir else ctx.NO_STANDARDS

    manifest_context = ctx.render_manifest_context(context)
    prompt_hash = template_hash(template)
    values = _shared_values(context, manifest_context, prompt_hash)
    values[ctx.TPL_DIMENSION_LIST] = ", ".join(dimensions)
    values[ctx.TPL_STANDARDS_CHECKLISTS] = standards_text
    return _render(template, context, values)
