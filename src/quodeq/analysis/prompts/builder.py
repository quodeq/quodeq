"""Prompt builder — assembles per-dimension analysis prompts from compass.md template."""
from __future__ import annotations

import logging

from quodeq.analysis.prompts import _context as ctx
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
from quodeq.analysis.prompts._template import load_template, template_hash
from quodeq.config.prompt_templates import render_template

_logger = logging.getLogger(__name__)

_TPL_EVALUATION_RULES = "EVALUATION_RULES"


def _load_evaluation_rules() -> str:
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
    "build_analysis_prompt",
    "build_consolidated_prompt",
    "load_template",
    "render_compiled_standards",
    "render_dimensions",
    "render_previous_findings_section",
    "_load_dimension_data",
]


def build_analysis_prompt(template: str, context: ctx.PromptContext) -> str:
    """Build a complete per-dimension analysis prompt from the template."""
    dimensions_text = render_dimensions(context.dimensions_data, context.dimension)
    prompt_hash = template_hash(template)

    standards_checklist = ctx.NO_STANDARDS
    if context.standards_dir:
        compiled_dir = context.standards_dir / "compiled"
        _eval_dir = context.evaluators_dir
        if compiled_dir.exists() or (_eval_dir and _eval_dir.is_dir()):
            if context.work_dir:
                compact = render_compact_standards(
                    compiled_dir, context.dimension, evaluators_dir=_eval_dir,
                )
                if compact != ctx.NO_STANDARDS_FOR_DIM:
                    standards_checklist = write_standards_and_instruction(
                        context.work_dir, context.dimension, compact,
                    )
                else:
                    standards_checklist = compact
            else:
                standards_checklist = render_compiled_standards(
                    compiled_dir, context.dimension, evaluators_dir=_eval_dir,
                )

    manifest_context = ctx.render_manifest_context(context)
    values = {
        ctx.TPL_DISCIPLINE: context.language,
        ctx.TPL_REPO_NAME: context.repo_name,
        ctx.TPL_DATE: context.date_str,
        ctx.TPL_DIMENSION: context.dimension,
        ctx.TPL_SOURCE_FILE_COUNT: str(context.source_file_count),
        ctx.TPL_STANDARDS_CHECKLIST: standards_checklist,
        ctx.TPL_ANALYSIS_GUIDANCE: manifest_context,
        "DIMENSIONS": dimensions_text,
        ctx.TPL_PROMPT_HASH: prompt_hash,
        ctx.TPL_SOURCE_MANIFEST: manifest_context,
        _TPL_EVALUATION_RULES: _load_evaluation_rules(),
    }
    if context.extra_vars:
        values.update(context.extra_vars)
    result = render_template(template, values)
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
    ) if context.standards_dir else ctx.NO_STANDARDS

    manifest_context = ctx.render_manifest_context(context)
    prompt_hash = template_hash(template)
    values = {
        ctx.TPL_DISCIPLINE: context.language,
        ctx.TPL_REPO_NAME: context.repo_name,
        ctx.TPL_DATE: context.date_str,
        ctx.TPL_DIMENSION_LIST: ", ".join(dimensions),
        ctx.TPL_SOURCE_FILE_COUNT: str(context.source_file_count),
        ctx.TPL_STANDARDS_CHECKLISTS: standards_text,
        ctx.TPL_ANALYSIS_GUIDANCE: manifest_context,
        ctx.TPL_PROMPT_HASH: prompt_hash,
        ctx.TPL_SOURCE_MANIFEST: manifest_context,
        _TPL_EVALUATION_RULES: _load_evaluation_rules(),
    }
    if context.extra_vars:
        values.update(context.extra_vars)
    return render_template(template, values)
