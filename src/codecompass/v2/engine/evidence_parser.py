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


def _judgment_to_dict(j: Judgment, practice_title: str = "") -> dict:
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
    # Include practice context in reason
    reason_parts = []
    if practice_title:
        reason_parts.append(practice_title)
    if j.reason:
        reason_parts.append(j.reason)
    if reason_parts:
        d["reason"] = " — ".join(reason_parts)
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

    Findings are grouped by sub_characteristic (e.g. Modularity, Analyzability)
    from the practice definitions. If a practice has no sub_characteristic,
    it falls back to grouping by practice ID.

    Args:
        jsonl_file: Path to JSONL file with evidence lines.
        plugin_id: Plugin identifier.
        repository: Repository name/path.
        date_str: Evaluation date.
        practices_data: Parsed practices.json for display names and metadata.
        source_file_count: Total source files in repo.
        files_read: Number of files the AI read during analysis.

    Returns:
        Populated Evidence object with PrincipleEvidence per sub-characteristic.
    """
    practice_lookup = _build_practice_lookup(practices_data)

    # Parse all judgments
    judgments: list[Judgment] = []
    content = jsonl_file.read_text() if jsonl_file.exists() else ""
    for line in content.splitlines():
        j = _parse_jsonl_line(line)
        if j is not None:
            judgments.append(j)

    # Group judgments by sub_characteristic
    sc_violations: dict[str, list[tuple[Judgment, str]]] = {}
    sc_compliance: dict[str, list[tuple[Judgment, str]]] = {}
    sc_severity: dict[str, str] = {}

    for j in judgments:
        practice_def = practice_lookup.get(j.practice_id, {})
        # Group by principle (new field), falling back to sub_characteristic (legacy), then practice_id
        principle = (
            practice_def.get("principle")
            or practice_def.get("sub_characteristic")
            or j.practice_id
        )
        practice_title = practice_def.get("title", j.practice_id)

        if j.verdict == "violation":
            sc_violations.setdefault(principle, []).append((j, practice_title))
        elif j.verdict == "compliance":
            sc_compliance.setdefault(principle, []).append((j, practice_title))

        # Track highest severity per principle — use judgment severity for standards findings
        sev = practice_def.get("severity") or j.severity or "medium"
        if principle not in sc_severity or _sev_rank(sev) > _sev_rank(sc_severity[principle]):
            sc_severity[principle] = sev

    # Build PrincipleEvidence per sub-characteristic
    all_sub_chars = set(sc_violations.keys()) | set(sc_compliance.keys())
    principles: dict[str, PrincipleEvidence] = {}

    for sc in sorted(all_sub_chars):
        pe = PrincipleEvidence(
            practice_id=sc,
            display_name=sc,
            dimension=judgments[0].dimension if judgments else "",
            severity=sc_severity.get(sc, "medium"),
            violations=[_judgment_to_dict(j, title) for j, title in sc_violations.get(sc, [])],
            compliance=[_judgment_to_dict(j, title) for j, title in sc_compliance.get(sc, [])],
        )
        pe.compute_metrics()
        principles[sc] = pe

    coverage_pct = round(files_read / source_file_count * 100, 1) if source_file_count > 0 else 0.0

    return Evidence(
        repository=repository,
        plugin_id=plugin_id,
        date=date_str,
        source_file_count=source_file_count,
        files_read=files_read,
        coverage_pct=coverage_pct,
        principles=principles,
        dismissed_count=0,
    )


_SEV_RANKS = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _sev_rank(sev: str) -> int:
    return _SEV_RANKS.get(sev, 1)
