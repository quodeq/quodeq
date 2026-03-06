"""Evidence parser — converts extracted JSONL lines into V2 Evidence model."""
from __future__ import annotations

import json
from pathlib import Path

from codecompass.v2.engine.evidence import Evidence, Judgment, PrincipleEvidence


def _parse_jsonl_line(line: str) -> Judgment | None:
    """Parse a single JSONL evidence line into a Judgment."""
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None

    practice_id = obj.get("p")
    verdict = obj.get("t")
    if not practice_id or verdict not in ("violation", "compliance"):
        return None

    return Judgment(
        practice_id=practice_id,
        verdict=verdict,
        dimension=obj.get("d", ""),
        file=obj.get("file", ""),
        line=obj.get("line", 0),
        snippet=obj.get("snippet", ""),
        severity=obj.get("severity", "medium"),
        violation_type=obj.get("vt", ""),
        reason=obj.get("reason", ""),
    )


def _judgment_to_dict(j: Judgment) -> dict:
    """Convert a Judgment to the dict format used in PrincipleEvidence lists."""
    d: dict = {"file": j.file}
    if j.line:
        d["line"] = j.line
    if j.snippet:
        d["snippet"] = j.snippet
    if j.severity:
        d["severity"] = j.severity
    if j.violation_type:
        d["violation_type"] = j.violation_type
    if j.reason:
        d["reason"] = j.reason
    return d


def _build_practice_lookup(practices_data: dict) -> dict[str, dict]:
    """Build a lookup from practice ID to practice definition."""
    return {p["id"]: p for p in practices_data.get("practices", [])}


def parse_jsonl_to_evidence(
    jsonl_file: Path,
    *,
    plugin_id: str,
    repository: str,
    date_str: str,
    practices_data: dict,
    source_file_count: int,
    files_read: int,
) -> Evidence:
    """Parse extracted JSONL file into a complete Evidence object.

    Args:
        jsonl_file: Path to JSONL file with evidence lines.
        plugin_id: Plugin identifier.
        repository: Repository name/path.
        date_str: Evaluation date.
        practices_data: Parsed practices.json for display names and metadata.
        source_file_count: Total source files in repo.
        files_read: Number of files the AI read during analysis.

    Returns:
        Populated Evidence object with PrincipleEvidence per practice.
    """
    practice_lookup = _build_practice_lookup(practices_data)

    # Group judgments by practice ID
    violations: dict[str, list[Judgment]] = {}
    compliance: dict[str, list[Judgment]] = {}
    dismissed = 0

    content = jsonl_file.read_text() if jsonl_file.exists() else ""
    for line in content.splitlines():
        j = _parse_jsonl_line(line)
        if j is None:
            continue
        if j.verdict == "violation":
            violations.setdefault(j.practice_id, []).append(j)
        elif j.verdict == "compliance":
            compliance.setdefault(j.practice_id, []).append(j)

    # Build PrincipleEvidence for each practice that has findings
    all_practice_ids = set(violations.keys()) | set(compliance.keys())
    principles: dict[str, PrincipleEvidence] = {}

    for pid in sorted(all_practice_ids):
        practice_def = practice_lookup.get(pid, {})
        pe = PrincipleEvidence(
            practice_id=pid,
            display_name=practice_def.get("title", pid),
            dimension=practice_def.get("dimension", ""),
            severity=practice_def.get("severity", "medium"),
            violations=[_judgment_to_dict(j) for j in violations.get(pid, [])],
            compliance=[_judgment_to_dict(j) for j in compliance.get(pid, [])],
        )
        pe.compute_metrics()
        principles[pid] = pe

    coverage_pct = round(files_read / source_file_count * 100, 1) if source_file_count > 0 else 0.0

    return Evidence(
        repository=repository,
        plugin_id=plugin_id,
        date=date_str,
        source_file_count=source_file_count,
        files_read=files_read,
        coverage_pct=coverage_pct,
        principles=principles,
        dismissed_count=dismissed,
    )
