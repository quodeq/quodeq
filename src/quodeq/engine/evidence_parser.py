"""Evidence parser — converts extracted JSONL lines into V2 Evidence model."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from quodeq.engine.evidence import Evidence, Judgment, PrincipleEvidence


@dataclass
class EvidenceContext:
    plugin_id: str
    repository: str
    date_str: str
    source_file_count: int
    files_read: int


def _build_cwe_name_lookup(standards_dir: Path) -> dict[int, str]:
    """Build CWE ID -> name from all compiled standards files."""
    lookup: dict[int, str] = {}
    compiled_dir = standards_dir / "compiled"
    if not compiled_dir.exists():
        return lookup
    for f in compiled_dir.glob("*.json"):
        data = json.loads(f.read_text())
        for principle in data.get("principles", []):
            for cwe in principle.get("cwes", []):
                cid = cwe.get("id")
                name = cwe.get("name", "")
                if isinstance(cid, int) and name and cid not in lookup:
                    lookup[cid] = name
    return lookup


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
        cwe=obj.get("cwe"),
    )


def _judgment_to_dict(j: Judgment, cwe_name: str = "", cwe_id: int | None = None) -> dict:
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
    if cwe_id:
        d["cwe"] = cwe_id
    if cwe_name:
        d["title"] = cwe_name
    reason_parts = []
    if cwe_name:
        reason_parts.append(cwe_name)
    if j.reason:
        reason_parts.append(j.reason)
    if reason_parts:
        d["reason"] = " — ".join(reason_parts)
    return d


def parse_jsonl_to_evidence(
    jsonl_file: Path,
    context: EvidenceContext,
    *,
    standards_dir: Path | None = None,
) -> Evidence:
    """Parse extracted JSONL file into a complete Evidence object.

    Findings are grouped by principle name (the p field the AI reports).
    CWE names are resolved from compiled standards when available.
    """
    plugin_id = context.plugin_id
    repository = context.repository
    date_str = context.date_str
    source_file_count = context.source_file_count
    files_read = context.files_read
    cwe_name_lookup = _build_cwe_name_lookup(standards_dir) if standards_dir else {}

    judgments: list[Judgment] = []
    content = jsonl_file.read_text() if jsonl_file.exists() else ""
    for line in content.splitlines():
        j = _parse_jsonl_line(line)
        if j is not None:
            judgments.append(j)

    sc_violations: dict[str, list[tuple[Judgment, str, int | None]]] = {}
    sc_compliance: dict[str, list[tuple[Judgment, str, int | None]]] = {}
    sc_severity: dict[str, str] = {}

    for j in judgments:
        principle = j.practice_id
        cwe_id = j.cwe
        cwe_name = cwe_name_lookup.get(cwe_id, "") if cwe_id is not None else ""

        if j.verdict == "violation":
            sc_violations.setdefault(principle, []).append((j, cwe_name, cwe_id))
        elif j.verdict == "compliance":
            sc_compliance.setdefault(principle, []).append((j, cwe_name, cwe_id))

        sev = j.severity or "medium"
        if principle not in sc_severity or _sev_rank(sev) > _sev_rank(sc_severity[principle]):
            sc_severity[principle] = sev

    all_principles = set(sc_violations.keys()) | set(sc_compliance.keys())
    principles: dict[str, PrincipleEvidence] = {}

    for sc in sorted(all_principles):
        pe = PrincipleEvidence(
            practice_id=sc,
            display_name=sc,
            dimension=judgments[0].dimension if judgments else "",
            severity=sc_severity.get(sc, "medium"),
            violations=[_judgment_to_dict(j, name, cid) for j, name, cid in sc_violations.get(sc, [])],
            compliance=[_judgment_to_dict(j, name, cid) for j, name, cid in sc_compliance.get(sc, [])],
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
