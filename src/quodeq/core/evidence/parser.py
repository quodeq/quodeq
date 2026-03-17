"""Evidence parser -- converts extracted JSONL lines into V2 Evidence model."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
import os
from pathlib import Path

from quodeq.core.evidence.model import Evidence, Judgment, PrincipleEvidence, compute_coverage_pct
from quodeq.shared.utils import open_text
from quodeq.engine._ref_utils import ref_label as _ref_label, load_compiled_refs

_logger = logging.getLogger(__name__)

_CWE_URL_TEMPLATE_DEFAULT = "https://cwe.mitre.org/data/definitions/{cwe_id}.html"


def _cwe_url_template(env: dict[str, str] | None = None) -> str:
    """Return the CWE URL template, reading from env lazily."""
    return (env or os.environ).get(
        "QUODEQ_CWE_URL_TEMPLATE",
        _CWE_URL_TEMPLATE_DEFAULT,
    )


def build_req_refs_lookup(compiled_dir: Path, dimension: str) -> dict[str, list[dict]]:
    """Return {req_id: [{label, url}, ...]} for all refs of each requirement.

    Delegates to _ref_utils.load_compiled_refs for the heavy lifting.
    """
    return load_compiled_refs(str(compiled_dir), dimension)


@dataclass
class EvidenceContext:
    """Metadata needed to construct an Evidence object from parsed JSONL."""
    language: str
    repository: str
    date_str: str
    source_file_count: int
    files_read: int
    module: str = ""


def resolve_llm_refs(
    llm_refs: list[str] | None,
    all_req_refs: list[dict] | None,
    cwe_url_template: str | None = None,
) -> list[dict] | None:
    """Filter req_refs to only those the LLM selected, building URLs for unknown labels.

    Only refs that carry a ``url`` are kept.  When the LLM did not select
    any refs (``llm_refs`` is None/empty), returns ``None`` rather than
    dumping all compiled refs — showing none is better than showing noise.

    *cwe_url_template* may be overridden for offline or internal deployments.
    """
    if not llm_refs:
        return None
    if cwe_url_template is None:
        cwe_url_template = _cwe_url_template()
    by_label = {r["label"]: r for r in (all_req_refs or [])}
    result = []
    upper_labels = {k.upper(): r for k, r in by_label.items()}
    for label in llm_refs:
        if label in by_label:
            result.append(by_label[label])
        elif label.upper().startswith("CWE-"):
            cwe_id = label.split("-", 1)[1]
            result.append({"label": label.upper(), "url": cwe_url_template.format(cwe_id=cwe_id)})
        else:
            # Prefix match: "CISQ-ASCRM-CWE-396" matches known label "CISQ"
            label_upper = label.upper()
            matched = next((r for k, r in upper_labels.items() if label_upper.startswith(k)), None)
            if matched:
                result.append(matched)
    # Only keep refs that have a URL -- drop bare labels without links
    result = [r for r in result if r.get("url")]
    return result if result else None


def _parse_jsonl_line(line: str) -> tuple[Judgment, list[str] | None] | None:
    """Parse a single JSONL evidence line into a Judgment and optional LLM ref selection."""
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        _logger.warning("Skipping malformed JSONL line: %s", exc)
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
    # Pre-resolved req_refs from MCP server enrichment take priority
    pre_resolved = obj.get("req_refs")
    if isinstance(pre_resolved, list) and pre_resolved:
        j.req_refs = pre_resolved
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


_SEV_RANKS = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _sev_rank(sev: str) -> int:
    return _SEV_RANKS.get(sev, 1)


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


def _enrich_judgment(
    j: Judgment,
    llm_refs: list[str] | None,
    compiled_dir: Path | None,
    req_refs_cache: dict[str, dict[str, list[dict]]],
) -> None:
    """Resolve and attach req_refs to a Judgment in-place."""
    if j.req_refs:
        return  # MCP server already enriched
    all_req_refs = None
    if compiled_dir and j.req and j.dimension:
        if j.dimension not in req_refs_cache:
            req_refs_cache[j.dimension] = build_req_refs_lookup(compiled_dir, j.dimension)
        all_req_refs = req_refs_cache[j.dimension].get(j.req)
    resolved = resolve_llm_refs(llm_refs, all_req_refs)
    if resolved:
        j.req_refs = resolved


def _read_judgments(
    jsonl_file: Path, compiled_dir: Path | None,
) -> list[Judgment]:
    """Read JSONL lines and return enriched Judgment objects."""
    if not jsonl_file.exists():
        return []
    judgments: list[Judgment] = []
    req_refs_cache: dict[str, dict[str, list[dict]]] = {}
    with open_text(jsonl_file) as _jf:
        for line in _jf:
            result = _parse_jsonl_line(line)
            if result is not None:
                j, llm_refs = result
                _enrich_judgment(j, llm_refs, compiled_dir, req_refs_cache)
                judgments.append(j)
    return judgments


def _build_principles(
    grouped: _GroupedJudgments, dimension_name: str,
) -> dict[str, PrincipleEvidence]:
    """Build scored PrincipleEvidence entries from grouped judgments."""
    all_principle_keys = set(grouped.violations.keys()) | set(grouped.compliance.keys())
    principles: dict[str, PrincipleEvidence] = {}
    for sc in sorted(all_principle_keys):
        pe = PrincipleEvidence(
            practice_id=sc,
            display_name=sc,
            dimension=dimension_name,
            severity=grouped.severity.get(sc, "medium"),
            violations=[_judgment_to_dict(j) for j in grouped.violations.get(sc, [])],
            compliance=[_judgment_to_dict(j) for j in grouped.compliance.get(sc, [])],
        )
        pe.compute_metrics()
        principles[sc] = pe
    return principles


def parse_jsonl_to_evidence(
    jsonl_file: Path,
    context: EvidenceContext,
    compiled_dir: Path | None = None,
) -> Evidence:
    """Parse extracted JSONL file into a complete Evidence object."""
    judgments = _read_judgments(jsonl_file, compiled_dir)
    grouped = _group_judgments(judgments)
    dimension_name = judgments[0].dimension if judgments else ""
    principles = _build_principles(grouped, dimension_name)

    source_file_count = context.source_file_count
    files_read = context.files_read
    coverage_pct = compute_coverage_pct(files_read, source_file_count)

    return Evidence(
        repository=context.repository,
        language=context.language,
        date=context.date_str,
        source_file_count=source_file_count,
        files_read=files_read,
        coverage_pct=coverage_pct,
        principles=principles,
        dismissed_count=0,
        module=context.module,
    )
