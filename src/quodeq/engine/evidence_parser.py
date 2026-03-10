"""Evidence parser — converts extracted JSONL lines into V2 Evidence model."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from quodeq.engine.evidence import Evidence, Judgment, PrincipleEvidence


@dataclass
class EvidenceContext:
    """Metadata needed to construct an Evidence object from parsed JSONL."""
    plugin_id: str
    repository: str
    date_str: str
    source_file_count: int
    files_read: int


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
        req=obj.get("req"),
        title=obj.get("w", ""),
    )


def _judgment_to_dict(j: Judgment) -> dict:
    """Convert a Judgment to the dict format used in PrincipleEvidence lists."""
    d: dict = {"file": j.file}
    _optional = {"line": j.line, "snippet": j.snippet, "severity": j.severity, "violation_type": j.violation_type}
    d.update({k: v for k, v in _optional.items() if v})
    if j.req:
        d["req"] = j.req
    if j.title:
        d["title"] = j.title
    if j.reason:
        d["reason"] = j.reason
    return d


@dataclass
class _GroupedJudgments:
    violations: dict[str, list[Judgment]]
    compliance: dict[str, list[Judgment]]
    severity: dict[str, str]


def _group_judgments(judgments: list[Judgment]) -> _GroupedJudgments:
    sc_violations: dict[str, list[Judgment]] = {}
    sc_compliance: dict[str, list[Judgment]] = {}
    sc_severity: dict[str, str] = {}

    for j in judgments:
        principle = j.practice_id
        if j.verdict == "violation":
            sc_violations.setdefault(principle, []).append(j)
        elif j.verdict == "compliance":
            sc_compliance.setdefault(principle, []).append(j)
        sev = j.severity or "medium"
        if principle not in sc_severity or _sev_rank(sev) > _sev_rank(sc_severity[principle]):
            sc_severity[principle] = sev

    return _GroupedJudgments(sc_violations, sc_compliance, sc_severity)


def parse_jsonl_to_evidence(
    jsonl_file: Path,
    context: EvidenceContext,
) -> Evidence:
    """Parse extracted JSONL file into a complete Evidence object."""
    judgments: list[Judgment] = []
    if jsonl_file.exists():
        with open(jsonl_file) as _jf:
            for line in _jf:
                j = _parse_jsonl_line(line)
                if j is not None:
                    judgments.append(j)

    grouped = _group_judgments(judgments)
    all_principles = set(grouped.violations.keys()) | set(grouped.compliance.keys())
    principles: dict[str, PrincipleEvidence] = {}

    for sc in sorted(all_principles):
        pe = PrincipleEvidence(
            practice_id=sc,
            display_name=sc,
            dimension=judgments[0].dimension if judgments else "",
            severity=grouped.severity.get(sc, "medium"),
            violations=[_judgment_to_dict(j) for j in grouped.violations.get(sc, [])],
            compliance=[_judgment_to_dict(j) for j in grouped.compliance.get(sc, [])],
        )
        pe.compute_metrics()
        principles[sc] = pe

    source_file_count = context.source_file_count
    files_read = context.files_read
    coverage_pct = round(files_read / source_file_count * 100, 1) if source_file_count > 0 else 0.0

    return Evidence(
        repository=context.repository,
        plugin_id=context.plugin_id,
        date=context.date_str,
        source_file_count=source_file_count,
        files_read=files_read,
        coverage_pct=coverage_pct,
        principles=principles,
        dismissed_count=0,
    )


_SEV_RANKS = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _sev_rank(sev: str) -> int:
    return _SEV_RANKS.get(sev, 1)
