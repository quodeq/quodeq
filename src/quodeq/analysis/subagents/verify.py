"""Mechanical verification — re-checks previous findings against current code.

Instead of one big AI agent re-exploring the codebase, iterate over each
previous finding mechanically:

1. Read the finding (file, line, snippet, principle)
2. Check if the file still exists and the code is still there
3. If confirmed, copy the finding to the current run's JSONL

Fast, zero AI tokens, runs in <1 second.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quodeq.data.fs.report_parser.runs import list_runs
from quodeq.analysis.prompts.builder import PromptContext, build_analysis_prompt, load_template
from quodeq.shared.logging import log_info, log_success
from quodeq.shared.utils import open_text

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


def _load_previous_findings(jsonl_path: Path) -> list[dict]:
    """Load all findings from a JSONL file."""
    findings: list[dict] = []
    if not jsonl_path.exists():
        return findings
    try:
        with open_text(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("p") and entry.get("t") in ("violation", "compliance"):
                        findings.append(entry)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return findings


def _mechanical_check(finding: dict, src: Path) -> str:
    """Check if a finding's code location still exists.

    Returns:
        "confirmed" — file and snippet still match
        "gone" — file deleted or line changed completely
        "ambiguous" — file exists but code changed, needs AI judgment
    """
    rel_path = finding.get("file", "")
    if not rel_path:
        return "gone"

    file_path = src / rel_path
    if not file_path.exists():
        return "gone"

    try:
        lines = file_path.read_text(errors="ignore").splitlines()
    except OSError:
        return "gone"

    target_line = finding.get("line", 0)
    snippet = finding.get("snippet", "").strip()

    if not snippet:
        # No snippet to match — file exists, assume ambiguous
        return "ambiguous"

    # Check exact line match first
    if 0 < target_line <= len(lines):
        line_content = lines[target_line - 1]
        if snippet in line_content or line_content.strip() in snippet:
            return "confirmed"

    # Check nearby lines (code may have shifted by a few lines)
    search_start = max(0, target_line - 10)
    search_end = min(len(lines), target_line + 10)
    for i in range(search_start, search_end):
        if snippet in lines[i] or lines[i].strip() in snippet:
            return "confirmed"

    # File exists but snippet not found nearby — code changed
    return "ambiguous"


def _write_finding(finding: dict, output_fh: Any) -> None:
    """Append a finding to the JSONL output file."""
    output_fh.write(json.dumps(finding) + "\n")
    output_fh.flush()


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
        lines.append(f"### {principle}")
        for finding in findings:
            t = finding.get("t", "?")
            file = finding.get("file", "?")
            line_num = finding.get("line", "?")
            severity = finding.get("severity", "?")
            desc = finding.get("w", "")
            lines.append(f"- {t} [{severity}] `{file}:{line_num}` — {desc}")
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
    return build_analysis_prompt(
        template,
        PromptContext(
            language=config.language,
            repo_name=str(config.src),
            date_str=ctx.date_str,
            dimension=dim_id,
            source_file_count=config.source_file_count,
            dimensions_data=ctx.dimensions_data,
            standards_dir=config.standards_dir,
            target=getattr(config, "target", None),
            extra_vars={"FINDINGS_SUMMARY": findings_summary},
        ),
    )


def _resolve_evidence_paths(evidence_dir: Path) -> tuple[str, str, Path] | None:
    """Walk up from evidence_dir to find run_id, project_uuid, reports_base."""
    edir = Path(evidence_dir)
    while edir.name != "evidence" and edir != edir.parent:
        edir = edir.parent
    if edir.name != "evidence":
        return None
    run_dir = edir.parent
    return run_dir.name, run_dir.parent.name, run_dir.parent.parent


def run_mechanical_verify(
    src: Path,
    prev_findings: list[dict],
    output_jsonl: Path,
) -> tuple[int, int, list[dict]]:
    """Mechanically verify findings against current code.

    Returns (confirmed_count, gone_count, ambiguous_findings).
    """
    confirmed = 0
    gone = 0
    ambiguous: list[dict] = []

    with open(output_jsonl, "a") as fh:
        for finding in prev_findings:
            status = _mechanical_check(finding, src)
            if status == "confirmed":
                _write_finding(finding, fh)
                confirmed += 1
            elif status == "gone":
                gone += 1
            else:
                ambiguous.append(finding)

    return confirmed, gone, ambiguous


def run_verify_for_dimension(
    config: Any,
    dim_id: str,
    evidence_dir: Path,
) -> int:
    """Run mechanical verification for a dimension.

    1. Find previous run's JSONL
    2. For each finding: check if file/snippet still exists
    3. Confirmed findings → copy to current JSONL
    4. Gone findings → drop
    5. Ambiguous findings → drop (conservative; analysis agents will re-discover if real)

    Returns number of findings carried forward.
    """
    if not getattr(config, 'options', None) or not config.options.verify_findings:
        return 0

    paths = _resolve_evidence_paths(evidence_dir)
    if paths is None:
        log_info(f"  [{dim_id}] Cannot locate evidence root — skipping verification")
        return 0

    current_run_id, project_uuid, reports_base = paths

    prev_jsonl = _find_previous_evidence(reports_base, project_uuid, current_run_id, dim_id)
    if prev_jsonl is None:
        log_info(f"  [{dim_id}] No previous evaluation — skipping verification")
        return 0

    prev_findings = _load_previous_findings(prev_jsonl)
    if not prev_findings:
        return 0

    log_info(f"  [{dim_id}] Verifying {len(prev_findings)} previous findings mechanically")

    output_jsonl = evidence_dir / f"{dim_id}_evidence.jsonl"
    confirmed, gone, ambiguous = run_mechanical_verify(config.src, prev_findings, output_jsonl)

    log_success(
        f"  [{dim_id}] Verification: {confirmed} confirmed, "
        f"{gone} gone, {len(ambiguous)} ambiguous (dropped)"
    )
    return confirmed
