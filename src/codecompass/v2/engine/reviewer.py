from __future__ import annotations

from pathlib import Path

from codecompass.config.generators import run_ai_cli
from codecompass.v2.engine.evidence import Judgment
from codecompass.v2.engine.file_sampler import SampledFile
from codecompass.v2.engine.judge import _parse_judge_output

_PROMPT_PATH = Path(__file__).parent / "prompts" / "reviewer.md"


def run_code_review(
    sampled_files: list[SampledFile],
    practices: dict,
    analysis_md: str,
    dimensions_config: dict,
    ai_caller=None,
    batch_size: int = 5,
) -> tuple[list[Judgment], int]:
    """Run LLM code review on batched source files.

    Returns (judgments, dismissed_count).
    """
    if ai_caller is None:
        ai_caller = run_ai_cli

    if not sampled_files:
        return [], 0

    prompt_template = _PROMPT_PATH.read_text()
    batches = _make_batches(sampled_files, batch_size)
    total_batches = len(batches)

    all_judgments: list[Judgment] = []
    total_dismissed = 0

    for i, batch in enumerate(batches, 1):
        context = _build_batch_context(batch, practices, analysis_md, dimensions_config, i, total_batches)
        prompt = prompt_template.replace("{{CONTEXT}}", context)

        try:
            stdout, error = ai_caller(prompt)
        except Exception:
            continue

        if error:
            continue

        judgments, dismissed = _parse_judge_output(stdout)

        # Tag all judgments with source = "code_review"
        for j in judgments:
            if not j.finding_rule:
                j.finding_rule = "code_review"

        all_judgments.extend(judgments)
        total_dismissed += dismissed

    return all_judgments, total_dismissed


def _make_batches(files: list[SampledFile], batch_size: int) -> list[list[SampledFile]]:
    return [files[i:i + batch_size] for i in range(0, len(files), batch_size)]


def _build_batch_context(
    batch: list[SampledFile],
    practices: dict,
    analysis_md: str,
    dimensions_config: dict,
    batch_num: int,
    total_batches: int,
) -> str:
    sections: list[str] = []

    sections.append(f"## Code Review — Batch {batch_num} of {total_batches}")

    # Practices section
    practice_list = practices.get("practices", [])
    if practice_list:
        lines = ["## Practices\n"]
        for p in practice_list:
            lines.append(f"### {p['id']}: {p['title']}")
            lines.append(f"- **Dimension:** {p['dimension']} | **Severity:** {p['severity']} | **CWE:** {p.get('cwe', 'N/A')}")
            lines.append(f"- **Bad:**\n```\n{p['bad']}\n```")
            lines.append(f"- **Good:**\n```\n{p['good']}\n```")
            lines.append(f"- **Why:** {p.get('explanation', '')}")
            lines.append("")
        sections.append("\n".join(lines))

    # Analysis guidance
    if analysis_md:
        sections.append(f"## Analysis Guidance\n\n{analysis_md}")

    # Source files section
    file_lines = ["## Source Files\n"]
    for sf in batch:
        trunc_note = " (TRUNCATED)" if sf.truncated else ""
        file_lines.append(f"### {sf.path} ({sf.lines} lines, selected: {sf.reason}){trunc_note}")
        file_lines.append(f"```\n{sf.content}\n```\n")
    sections.append("\n".join(file_lines))

    return "\n\n---\n\n".join(sections)
