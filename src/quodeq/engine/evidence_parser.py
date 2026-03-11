"""Evidence parser — converts extracted JSONL lines into V2 Evidence model."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from quodeq.engine.evidence import Evidence, Judgment, PrincipleEvidence


def _ref_label(ref: dict) -> str:
    """Build a display label for a ref (e.g. 'CWE-396', 'ERR08-J', 'WCAG 1.1.1')."""
    source = ref.get("source", "")
    ref_id = ref.get("id")
    if source == "cwe" and ref_id:
        return f"CWE-{ref_id}"
    if source == "wcag22" and ref_id:
        return f"WCAG {ref_id}"
    if source == "asvs" and ref_id:
        return f"ASVS {ref_id}"
    if ref_id:
        return ref_id
    return source.upper() if source else "REF"


def _build_req_refs_lookup(compiled_dir: Path, dimension: str) -> dict[str, list[dict]]:
    """Return {req_id: [{label, url}, ...]} for all refs of each requirement."""
    try:
        dim_file = compiled_dir / f"{dimension}.json"
        data = json.loads(dim_file.read_text())
    except Exception:
        return {}

    lookup: dict[str, list[dict]] = {}
    for principle in data.get("principles", []):
        for req in principle.get("requirements", []):
            req_id = req.get("id")
            if not req_id:
                continue
            refs = []
            for ref in req.get("refs", []):
                url = ref.get("url")
                if url:
                    refs.append({"label": _ref_label(ref), "url": url})
            if refs:
                lookup[req_id] = refs
    return lookup


@dataclass
class EvidenceContext:
    """Metadata needed to construct an Evidence object from parsed JSONL."""
    plugin_id: str
    repository: str
    date_str: str
    source_file_count: int
    files_read: int


def _resolve_llm_refs(llm_refs: list[str] | None, all_req_refs: list[dict] | None) -> list[dict] | None:
    """Filter req_refs to only those the LLM selected, building URLs for unknown labels.

    Only refs that carry a ``url`` are kept.  If nothing with a URL remains
    after filtering, *all_req_refs* is returned so the caller always gets
    the compiled CWE/CISQ references.
    """
    if not llm_refs:
        return all_req_refs
    by_label = {r["label"]: r for r in (all_req_refs or [])}
    result = []
    for label in llm_refs:
        if label in by_label:
            result.append(by_label[label])
        elif label.upper().startswith("CWE-"):
            cwe_id = label.split("-", 1)[1]
            result.append({"label": label.upper(), "url": f"https://cwe.mitre.org/data/definitions/{cwe_id}.html"})
        else:
            # Prefix match: "CISQ-ASCRM-CWE-396" matches known label "CISQ"
            matched = next((r for k, r in by_label.items() if label.upper().startswith(k.upper())), None)
            if matched:
                result.append(matched)
    # Only keep refs that have a URL — drop bare labels without links
    result = [r for r in result if r.get("url")]
    return result if result else all_req_refs


def _parse_jsonl_line(line: str) -> tuple[Judgment, list[str] | None] | None:
    """Parse a single JSONL evidence line into a Judgment and optional LLM ref selection."""
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

    j = Judgment(
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
    return j, obj.get("refs")


def _judgment_to_dict(j: Judgment) -> dict:
    """Convert a Judgment to the dict format used in PrincipleEvidence lists."""
    d: dict = {"file": j.file}
    _optional = {"line": j.line, "snippet": j.snippet, "severity": j.severity, "violation_type": j.violation_type}
    d.update({k: v for k, v in _optional.items() if v})
    if j.req:
        d["req"] = j.req
    if j.req_refs:
        d["req_refs"] = j.req_refs
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
    compiled_dir: Path | None = None,
) -> Evidence:
    """Parse extracted JSONL file into a complete Evidence object."""
    judgments: list[Judgment] = []
    req_refs_cache: dict[str, dict[str, list[dict]]] = {}
    if jsonl_file.exists():
        with open(jsonl_file) as _jf:
            for line in _jf:
                result = _parse_jsonl_line(line)
                if result is not None:
                    j, llm_refs = result
                    all_req_refs = None
                    if compiled_dir and j.req and j.dimension:
                        if j.dimension not in req_refs_cache:
                            req_refs_cache[j.dimension] = _build_req_refs_lookup(compiled_dir, j.dimension)
                        all_req_refs = req_refs_cache[j.dimension].get(j.req)
                    resolved = _resolve_llm_refs(llm_refs, all_req_refs)
                    if resolved:
                        j.req_refs = resolved
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
