from __future__ import annotations

import json

from codecompass.evaluate.lib.common import log_warning


def _sub(template: str, **kwargs: str) -> str:
    """Replace {{KEY}} placeholders in a template string."""
    result = template
    for key, value in kwargs.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


def build_analysis_jsonl_prompt(
    template: str,
    discipline: str,
    project_name: str,
    today: str,
    standards_content: str,
    source_file_count: int = 0,
    analysis_hash: str = "",
    prescan_metrics: str = "",
    prescan_guidance: str = "",
    limited_scope_discipline: str = "",
    limited_scope_dimension: str = "",
    multi_target_context: str = "",
    current_target_name: str = "",
    current_target_path: str = "",
) -> str:
    """Build the JSONL streaming analysis prompt."""
    prompt = _sub(
        template,
        DISCIPLINE=discipline,
        REPO_NAME=project_name,
        DATE=today,
        SOURCE_FILE_COUNT=str(source_file_count),
        ANALYSIS_PROMPT_HASH=analysis_hash,
    )

    if multi_target_context:
        target_context = (
            f"\n{multi_target_context}\n\n"
            f'This evaluation targets "{current_target_name}" ({current_target_path}).\n\n'
            "Consider cross-boundary concerns where relevant:\n"
            "  - API contract alignment between this target and sibling targets\n"
            "  - Shared dependencies or code duplication across targets\n"
            "  - Integration points (imports, API calls, shared types)\n\n"
            f"Focus your analysis on code within {current_target_path}. Reference sibling targets\n"
            "only when evaluating coupling, integration, or architectural coherence."
        )
        prompt = f"{target_context}\n\n{prompt}"

    if limited_scope_discipline:
        limited_note = (
            f"NOTE: This dimension ({limited_scope_dimension}) has limited applicability to "
            f"{limited_scope_discipline} codebases. Focus only on requirements that are directly "
            f"observable in {limited_scope_discipline} code. Skip or note as N/A any sub-criteria "
            "that are fundamentally not relevant to this discipline."
        )
        prompt = f"{limited_note}\n\n{prompt}"

    if prescan_metrics or prescan_guidance:
        prescan_block = prescan_metrics
        if prescan_guidance:
            prescan_block = f"{prescan_block}\n\n{prescan_guidance}" if prescan_block else prescan_guidance
        prompt = f"{prescan_block}\n\n{prompt}"

    return f"{prompt}\n{standards_content}\n"


def _build_scoring_skeleton(evidence_data: dict, is_numerical: bool) -> str:
    """Build a pre-populated markdown scoring table from evidence principles."""
    principles = evidence_data.get("principles", {})
    if is_numerical:
        lines = [
            "| Principle | Compliance% | Band | Deductions | Score | Grade |",
            "|-----------|------------|------|------------|-------|-------|",
        ]
        for p_key, p_data in principles.items():
            name = p_data.get("display_name", p_key)
            lines.append(f"| {name} | | | | | |")
        lines.append("| **Overall** | | | | **_/10** | **_** |")
    else:
        lines = [
            "| Principle | Compliance Level | Adjustments | Grade |",
            "|-----------|-----------------|-------------|-------|",
        ]
        for p_key, p_data in principles.items():
            name = p_data.get("display_name", p_key)
            lines.append(f"| {name} | | | |")
        lines.append("| **Overall** | | | **_** |")
    return "\n".join(lines)


def detect_scoring_mode(template: str) -> str:
    """Detect scoring mode from the template content.

    Returns 'non-numerical' if the template contains 'non-numerical',
    otherwise 'numerical'.
    """
    return "non-numerical" if "non-numerical" in template.lower() else "numerical"


def build_scoring_prompt(
    template: str,
    discipline: str,
    project_name: str,
    today: str,
    eval_file: str,
    standards_content: str,
    dimension: str,
    evidence_content: str = "",
    scores_content: str = "",
    analysis_hash: str = "",
    scoring_hash: str = "",
    mapping_hash: str = "",
    codecompass_version: str = "",
    scoring_mode: str = "",
) -> str:
    """Build the scoring prompt with evidence injection."""
    prompt = _sub(
        template,
        DISCIPLINE=discipline,
        DIMENSION=dimension,
        REPO_NAME=project_name,
        DATE=today,
        ANALYSIS_PROMPT_HASH=analysis_hash,
        SCORING_PROMPT_HASH=scoring_hash,
        MAPPING_FILE_HASH=mapping_hash,
        CODECOMPASS_VERSION=codecompass_version,
    )

    # Build and inject scoring skeleton
    evidence_data: dict = {}
    if evidence_content:
        try:
            evidence_data = json.loads(evidence_content)
        except Exception as exc:
            log_warning(f"Could not parse evidence content: {exc}")

    effective_mode = scoring_mode if scoring_mode else detect_scoring_mode(prompt)
    is_numerical = effective_mode == "numerical"
    skeleton = _build_scoring_skeleton(evidence_data, is_numerical)
    prompt = prompt.replace("{{SCORING_SKELETON}}", skeleton)

    # Inject precomputed scores
    effective_scores = scores_content if scores_content else "No precomputed scores available — compute scores manually using the rules below."
    prompt = prompt.replace("{{PRECOMPUTED_SCORES_JSON}}", effective_scores)

    # Inject evidence JSON
    evidence_json = json.dumps(evidence_data, indent=2) if evidence_data else "{}"
    prompt = prompt.replace("{{EVIDENCE_JSON}}", evidence_json)

    return f"{prompt}\n{standards_content}\n"
