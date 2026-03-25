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

from quodeq.analysis.subagents._verify_pool import build_verify_prompt  # noqa: F401 — re-export
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


def _classify_findings(
    findings: list[dict], prev_hashes: dict, src: Path,
) -> tuple[list[dict], list[dict]]:
    """Classify findings into carry-forward vs needs-verification by file hash."""
    from quodeq.analysis.fingerprint import _hash_file
    file_unchanged: dict[str, bool] = {}
    carry_forward: list[dict] = []
    needs_verification: list[dict] = []
    for finding in findings:
        rel_path = finding.get("file", "")
        if not rel_path:
            needs_verification.append(finding)
            continue
        if rel_path not in file_unchanged:
            prev_hash = prev_hashes.get(rel_path)
            if prev_hash is None:
                file_unchanged[rel_path] = False
            else:
                file_unchanged[rel_path] = _hash_file(src / rel_path) == prev_hash
        if file_unchanged[rel_path]:
            carry_forward.append(finding)
        else:
            needs_verification.append(finding)
    return carry_forward, needs_verification


def partition_findings_by_fingerprint(
    findings: list[dict],
    prev_fingerprint: dict | None,
    src: Path,
    standards_dir: Path | None = None,
    dimension: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Split findings into (carry_forward, needs_verification) based on file hashes.

    Uses the previous fingerprint's per-file SHA-256 hashes to determine which
    files have changed. Findings for unchanged files are carried forward (no AI
    needed); findings for changed/deleted/new files need AI verification.

    If standards changed since the previous run, all findings need verification
    regardless of file hashes (findings were evaluated under different criteria).
    """
    from quodeq.analysis.fingerprint import _hash_standards

    if not prev_fingerprint or not findings:
        return [], list(findings)

    # Standards guard: if standards changed, all findings need verification
    if standards_dir and dimension:
        current_std = _hash_standards(standards_dir, dimension)
        prev_std = prev_fingerprint.get("standards_checksum")
        if prev_std is not None and current_std != prev_std:
            return [], list(findings)

    return _classify_findings(findings, prev_fingerprint.get("file_hashes", {}), src)


def write_carry_forward_findings(
    findings: list[dict], evidence_dir: Path, dim_id: str,
) -> int:
    """Append carry-forward findings to the evidence JSONL.

    Writes from an in-memory list of finding dicts (as returned by
    partition_findings_by_fingerprint). Unlike carry_forward_findings in
    incremental.py which filters file-to-file, this writes pre-partitioned
    results directly.

    Returns the number of findings written.
    """
    if not findings:
        return 0
    output = evidence_dir / f"{dim_id}_evidence.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "a") as f:
        for finding in findings:
            f.write(json.dumps(finding) + "\n")
    return len(findings)


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


def _resolve_evidence_paths(evidence_dir: Path) -> tuple[str, str, Path] | None:
    """Walk up from evidence_dir to find run_id, project_uuid, reports_base."""
    edir = Path(evidence_dir)
    while edir.name != "evidence" and edir != edir.parent:
        edir = edir.parent
    if edir.name != "evidence":
        return None
    run_dir = edir.parent
    return run_dir.name, run_dir.parent.name, run_dir.parent.parent


def _resolve_previous_evidence(
    evidence_dir: Path,
    dim_id: str,
    cache: dict[tuple[str, str], tuple[list[dict], int, int]] | None,
    cache_key: tuple[str, str],
) -> tuple[Path | None, bool]:
    """Resolve path to the previous evidence JSONL file.

    Returns (prev_jsonl_path, already_cached).  When *already_cached* is True
    the caller should use the cache hit instead.  A ``None`` path means no
    previous evidence exists.
    """
    paths = _resolve_evidence_paths(evidence_dir)
    if paths is None:
        if cache is not None:
            cache[cache_key] = ([], 0, 0)
        return None, False
    current_run_id, project_uuid, reports_base = paths
    prev_jsonl = _find_previous_evidence(reports_base, project_uuid, current_run_id, dim_id)
    if prev_jsonl is None:
        if cache is not None:
            cache[cache_key] = ([], 0, 0)
        return None, False
    return prev_jsonl, False


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
                log_info(f"  [{dim_id}] {total} previous findings: {gone} files gone, {len(surviving)} surviving")
            return surviving

    prev_jsonl, _ = _resolve_previous_evidence(evidence_dir, dim_id, cache, cache_key)
    if prev_jsonl is None:
        if not quiet:
            log_info(f"  [{dim_id}] No previous evaluation — skipping verification")
        return []

    prev_findings = _load_previous_findings(prev_jsonl)
    if not prev_findings:
        if cache is not None:
            cache[cache_key] = ([], 0, 0)
        return []

    surviving, gone = _pre_filter_gone(prev_findings, config.src)
    if not quiet:
        log_info(f"  [{dim_id}] {len(prev_findings)} previous findings: {gone} files gone, {len(surviving)} surviving")
    if cache is not None:
        cache[cache_key] = (surviving, len(prev_findings), gone)
    return surviving
