"""Post-analysis verification pass — re-checks previous run's findings for consistency."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quodeq.analysis.subprocess import AnalysisConfig, run_analysis
from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl
from quodeq.data.fs.report_parser.runs import list_runs
from quodeq.engine.evidence import Evidence
from quodeq.engine.prompt_builder import PromptContext, build_analysis_prompt, load_template
from quodeq.shared.logging import log_info, log_success, log_warning
from quodeq.shared.utils import open_text

_DEFAULT_VERIFY_AGENTS = 1
_DEFAULT_VERIFY_BUDGET = 300  # 5 minutes per verifier
_VERIFY_TEMPLATE = "verify.md"


def _find_previous_evidence(reports_root: Path, project_uuid: str, current_run_id: str, dim_id: str) -> Path | None:
    """Find the JSONL evidence file from the most recent previous run."""
    runs = list_runs(reports_root, project_uuid)
    for run in runs:
        if run.run_id == current_run_id:
            continue
        prev_jsonl = reports_root / project_uuid / run.run_id / "evidence" / f"{dim_id}_evidence.jsonl"
        if prev_jsonl.exists() and prev_jsonl.stat().st_size > 0:
            return prev_jsonl
    return None


def _format_findings_summary(jsonl_path: Path) -> str:
    """Format findings from a JSONL file into a readable summary for verifiers."""
    if not jsonl_path.exists():
        return "_No findings from previous evaluation._"

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
        return "_Could not read previous findings._"

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

    return "\n".join(lines) if lines else "_No findings from previous evaluation._"


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
    """Re-check the previous run's findings against the current code.

    Reads violations/compliance from the most recent previous evaluation,
    then launches verification agents that confirm which are still present
    and hunt for missing compliance evidence. New findings are appended to
    the current run's JSONL (dedup prevents duplicates).

    Returns the number of new findings added, or 0 if no previous run exists.
    """
    # Find the previous run's evidence
    reports_root = Path(config.work_dir or evidence_dir).parent.parent
    current_run_id = Path(config.work_dir or evidence_dir).parent.name
    project_uuid = reports_root.name
    reports_base = reports_root.parent

    prev_jsonl = _find_previous_evidence(reports_base, project_uuid, current_run_id, dim_id)
    if prev_jsonl is None:
        log_info(f"  [{dim_id}] No previous evaluation found — skipping verification")
        return 0

    findings_summary = _format_findings_summary(prev_jsonl)
    if "_No findings" in findings_summary:
        return 0

    jsonl_path = evidence_dir / f"{dim_id}_evidence.jsonl"
    prompt = _build_verify_prompt(config, dim_id, ctx, findings_summary)
    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None

    # Count findings before verification
    before_count = _count_findings(jsonl_path)

    log_info(f"  [{dim_id}] Verifying previous run findings ({n_agents} agents)")

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
    log_success(f"  [{dim_id}] Verification complete: +{new_findings} findings from previous run check")
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
