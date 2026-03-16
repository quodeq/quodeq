"""Post-analysis verification pass — re-checks findings and hunts for compliance."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quodeq.analysis.subprocess import AnalysisConfig, run_analysis
from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl
from quodeq.engine.evidence import Evidence
from quodeq.engine.prompt_builder import PromptContext, build_analysis_prompt, load_template
from quodeq.shared.logging import log_info, log_success
from quodeq.shared.utils import open_text

_DEFAULT_VERIFY_AGENTS = 1
_DEFAULT_VERIFY_BUDGET = 300  # 5 minutes per verifier
_VERIFY_TEMPLATE = "verify.md"


def _format_findings_summary(jsonl_path: Path) -> str:
    """Format first-pass findings into a readable summary for verifiers."""
    if not jsonl_path.exists():
        return "_No findings from first pass._"

    by_principle: dict[str, list[dict]] = {}
    try:
        with open_text(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                principle = entry.get("p", "unknown")
                by_principle.setdefault(principle, []).append(entry)
    except OSError:
        return "_Could not read first-pass findings._"

    lines: list[str] = []
    for principle, findings in sorted(by_principle.items()):
        violations = [f for f in findings if f.get("t") == "violation"]
        compliances = [f for f in findings if f.get("t") == "compliance"]
        lines.append(f"### {principle} ({len(violations)}v / {len(compliances)}c)")
        for f in violations[:10]:  # cap to keep prompt manageable
            file = f.get("file", "?")
            line_num = f.get("line", "?")
            desc = f.get("w", "")
            severity = f.get("severity", "?")
            lines.append(f"- **{severity}** `{file}:{line_num}` — {desc}")
        if len(violations) > 10:
            lines.append(f"- _...and {len(violations) - 10} more violations_")
        lines.append("")

    return "\n".join(lines) if lines else "_No findings from first pass._"


def _build_verify_prompt(
    config: Any,
    dim_id: str,
    ctx: Any,
    findings_summary: str,
) -> str:
    """Build a verification prompt from the verify.md template."""
    template = load_template(template_name=_VERIFY_TEMPLATE)
    prompt = build_analysis_prompt(
        template,
        PromptContext(
            plugin_id=config.plugin_id,
            repo_name=str(config.src),
            date_str=ctx.date_str,
            dimension=dim_id,
            source_file_count=config.source_file_count,
            dimensions_data=ctx.dimensions_data,
            analysis_md="",  # verifiers don't need analysis guidance
            standards_dir=config.standards_dir,
        ),
    )
    # Inject the findings summary (not a standard template var)
    prompt = prompt.replace("{{FINDINGS_SUMMARY}}", findings_summary)
    return prompt


def run_verification_pass(
    config: Any,
    dim_id: str,
    ctx: Any,
    evidence_dir: Path,
    *,
    n_agents: int = _DEFAULT_VERIFY_AGENTS,
    max_duration: int = _DEFAULT_VERIFY_BUDGET,
) -> int:
    """Run verification agents that re-check findings and add compliance evidence.

    Appends to the existing JSONL file. Returns the number of new findings added.
    """
    jsonl_path = evidence_dir / f"{dim_id}_evidence.jsonl"
    findings_summary = _format_findings_summary(jsonl_path)

    if "_No findings" in findings_summary:
        return 0

    prompt = _build_verify_prompt(config, dim_id, ctx, findings_summary)
    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None

    # Count findings before verification
    before_count = _count_findings(jsonl_path)

    log_info(f"  [{dim_id}] Starting verification pass ({n_agents} agents)")

    for i in range(n_agents):
        stream_file = evidence_dir / f"{dim_id}_verify_{i}.stream"
        ac = AnalysisConfig(
            jsonl_file=jsonl_path,
            compiled_dir=compiled_dir,
            dimension=dim_id,
            max_duration=max_duration,
            agent_id=f"verify-{i}",
        )
        try:
            run_analysis(
                work_dir=config.src,
                prompt=prompt,
                stream_file=stream_file,
                config=ac,
            )
        except Exception as exc:
            log_info(f"  [{dim_id}] Verifier {i} finished with: {exc}")

    # Deduplicate after all verifiers have appended
    deduplicate_jsonl(jsonl_path)

    after_count = _count_findings(jsonl_path)
    new_findings = after_count - before_count
    log_success(f"  [{dim_id}] Verification complete: +{new_findings} new findings")
    return new_findings


def _count_findings(jsonl_path: Path) -> int:
    """Count non-empty lines in a JSONL file."""
    if not jsonl_path.exists():
        return 0
    try:
        with open_text(jsonl_path) as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0
