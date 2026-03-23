"""Finding verification — re-checks previous findings using a fast AI pool.

Two-phase approach:
1. Mechanical pre-filter: drop findings whose files no longer exist (instant)
2. AI verification pool: dispatch remaining findings to fast model subagents
   grouped by file, each agent reads the current code and confirms/drops

Confirmed findings are written to the evidence JSONL via MCP (same as
main analysis), so they appear on the dashboard immediately.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quodeq.data.fs.report_parser.runs import list_runs
from quodeq.shared.logging import log_debug, log_info, log_success
from quodeq.shared.utils import open_text


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


def _parse_finding_line(line: str) -> dict | None:
    """Parse a single JSONL line into a finding dict, or None if invalid."""
    line = line.strip()
    if not line:
        return None
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        return None
    if entry.get("p") and entry.get("t") in ("violation", "compliance"):
        return entry
    return None


def _load_previous_findings(jsonl_path: Path) -> list[dict]:
    """Load all findings from a JSONL file."""
    if not jsonl_path.exists():
        return []
    try:
        with open_text(jsonl_path) as f:
            return [e for line in f if (e := _parse_finding_line(line)) is not None]
    except OSError as exc:
        log_debug(f"Cannot read findings JSONL {jsonl_path}: {exc}")
        return []


def _pre_filter_gone(findings: list[dict], src: Path) -> tuple[list[dict], int]:
    """Fast pre-filter: drop findings whose files no longer exist.

    Returns (surviving_findings, gone_count).
    """
    # Batch existence checks: resolve unique paths once instead of per-finding.
    unique_paths: dict[str, bool] = {}
    for finding in findings:
        rel_path = finding.get("file", "")
        if rel_path and rel_path not in unique_paths:
            unique_paths[rel_path] = (src / rel_path).exists()

    surviving: list[dict] = []
    gone = 0
    for finding in findings:
        rel_path = finding.get("file", "")
        if not rel_path or not unique_paths.get(rel_path, False):
            gone += 1
        else:
            surviving.append(finding)
    return surviving, gone


def _group_by_file(findings: list[dict]) -> dict[str, list[dict]]:
    """Group findings by their source file path."""
    groups: dict[str, list[dict]] = {}
    for finding in findings:
        file_path = finding.get("file", "")
        if file_path:
            groups.setdefault(file_path, []).append(finding)
    return groups


def _write_verify_manifest(
    grouped: dict[str, list[dict]],
    output_path: Path,
) -> None:
    """Write the verification manifest — a JSON file mapping files to findings.

    Each verification subagent reads this to know which findings to re-check.
    """
    output_path.write_text(json.dumps(grouped, indent=2))


_VERIFY_PROMPT_TEMPLATE = """\
You are re-verifying previous evaluation findings against the current codebase.
This is a quick verification pass — be fast and decisive.

## Task

For each file in the verification manifest at `{manifest_path}`:
1. Read the file from the queue
2. Look up its findings in the manifest
3. For each finding, check if the violation/compliance condition **still applies**
   to the current code — not just whether the line exists, but whether the
   underlying issue is still present
4. If the finding still applies, report it using the `report_finding` tool
   with the same fields (principle, type, severity, file, line, reason, snippet)
5. If the issue has been fixed or no longer applies, skip it silently

## Important

- Do NOT discover new findings — only verify existing ones
- Do NOT modify any files
- Read each file, check the findings, report confirmed ones, move on
- Be fast — this should take seconds per file

Dimension: {dimension}
"""


def build_verify_prompt(manifest_path: Path, dimension: str) -> str:
    """Build the prompt for verification subagents."""
    return _VERIFY_PROMPT_TEMPLATE.format(
        manifest_path=manifest_path,
        dimension=dimension,
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


def load_previous_findings_for_dimension(
    config: Any,
    dim_id: str,
    evidence_dir: Path,
    *,
    quiet: bool = False,
    cache: dict[tuple[str, str], tuple[list[dict], int, int]] | None = None,
) -> list[dict]:
    """Load and pre-filter previous findings for a dimension.

    When *cache* is provided, results are stored per (evidence_dir, dim_id)
    so multiple callers (priority scoring, verification) don't repeat file
    I/O within the same run.  Pass ``None`` to disable caching.

    Returns list of findings to verify (may be empty).
    """
    if not getattr(config, 'options', None) or not config.options.verify_findings:
        return []

    cache_key = (str(evidence_dir), dim_id)
    if cache is not None:
        cached = cache.get(cache_key)
        if cached is not None:
            surviving, total, gone = cached
            if not quiet and total > 0:
                log_info(
                    f"  [{dim_id}] {total} previous findings: "
                    f"{gone} files gone, {len(surviving)} to verify"
                )
            return surviving

    paths = _resolve_evidence_paths(evidence_dir)
    if paths is None:
        if cache is not None:
            cache[cache_key] = ([], 0, 0)
        return []

    current_run_id, project_uuid, reports_base = paths

    prev_jsonl = _find_previous_evidence(reports_base, project_uuid, current_run_id, dim_id)
    if prev_jsonl is None:
        if not quiet:
            log_info(f"  [{dim_id}] No previous evaluation — skipping verification")
        if cache is not None:
            cache[cache_key] = ([], 0, 0)
        return []

    prev_findings = _load_previous_findings(prev_jsonl)
    if not prev_findings:
        if cache is not None:
            cache[cache_key] = ([], 0, 0)
        return []

    surviving, gone = _pre_filter_gone(prev_findings, config.src)
    if not quiet:
        log_info(
            f"  [{dim_id}] {len(prev_findings)} previous findings: "
            f"{gone} files gone, {len(surviving)} to verify"
        )
    if cache is not None:
        cache[cache_key] = (surviving, len(prev_findings), gone)
    return surviving
