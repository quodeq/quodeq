"""Low-level JSONL parsing for evidence judgments."""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from quodeq.core.constants import FULL_CONFIDENCE
from quodeq.core.evidence._options import EvidenceParseOptions, MalformedLineSink
from quodeq.core.evidence.refs import enrich_judgment, resolve_llm_refs
from quodeq.core.finding_builder import FindingSpec, build_finding_base
from quodeq.core.finding_coercions import coerce_confidence, coerce_scope_downgrade
from quodeq.core.events.models import DEFAULT_SEVERITY, Judgment
from quodeq.core.types.finding import Finding
from quodeq.core.types.finding_type import FINDING_TYPES
from quodeq.core.types.req_ref import ReqRef
from quodeq.core.utils.io import open_text


def parse_jsonl_line(
    line: str, *, on_malformed_line: MalformedLineSink | None = None,
) -> tuple[Judgment, list[str] | None] | None:
    """Parse a single JSONL evidence line into a Judgment and optional LLM ref selection."""
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        if on_malformed_line is not None:
            on_malformed_line(f"Skipping malformed JSONL line: {exc}")
        return None
    if not isinstance(obj, dict):
        if on_malformed_line is not None:
            on_malformed_line("Skipping non-object JSONL line")
        return None

    practice_id = obj.get("p") or obj.get("req")
    verdict = obj.get("t")
    if not practice_id or verdict not in FINDING_TYPES:
        return None

    pre_resolved = obj.get("req_refs")
    req_refs: list[ReqRef] = []
    if isinstance(pre_resolved, list):
        req_refs = [
            ReqRef(label=r.get("label", ""), url=r.get("url", ""))
            for r in pre_resolved if isinstance(r, dict)
        ]

    j = Judgment(
        practice_id=practice_id, verdict=verdict, dimension=obj.get("d", ""),
        file=obj.get("file", ""), line=obj.get("line", 0), end_line=obj.get("end_line"),
        snippet=obj.get("snippet", ""), severity=obj.get("severity", DEFAULT_SEVERITY),
        violation_type=obj.get("vt") or None, reason=obj.get("reason", ""),
        violation_type_raw=obj.get("vt_raw") or None,
        req=obj.get("req"), title=obj.get("w") or None,
        context=obj.get("context") or None, scope=obj.get("scope") or None,
        confidence=coerce_confidence(obj.get("confidence")),
        req_refs=req_refs,
        provenance_downgrade=bool(obj.get("provenance_downgrade")),
        scope_downgrade=coerce_scope_downgrade(obj.get("scope_downgrade")),
        carried_forward=bool(obj.get("carried_forward")),
    )
    return j, obj.get("refs")


def build_finding_entry(
    obj: dict, dimension: str, req_refs_lookup: dict[str, list[dict]] | None = None,
) -> Finding:
    """Build a normalized finding from a raw JSON object."""
    req = obj.get("req")
    # Prefer MCP-enriched req_refs (already filtered to best-match);
    # fall back to compiled-standards lookup + LLM ref selection.
    pre_resolved = obj.get("req_refs")
    if isinstance(pre_resolved, list) and pre_resolved:
        req_refs = pre_resolved
    else:
        all_req_refs = req_refs_lookup.get(req) if req and req_refs_lookup else None
        req_refs = resolve_llm_refs(obj.get("refs"), all_req_refs)
    entry = build_finding_base(FindingSpec(
        practice_id=obj["p"],
        file=obj.get("file"),
        line=obj.get("line"),
        end_line=obj.get("end_line"),
        title=obj.get("w"),
        reason=obj.get("reason"),
        snippet=obj.get("snippet"),
        severity=obj.get("severity"),
        cwe=obj.get("cwe"),
        req=req,
        req_refs=req_refs,
        context=obj.get("context"),
        scope=obj.get("scope"),
        confidence=coerce_confidence(obj.get("confidence")),
        provenance_downgrade=bool(obj.get("provenance_downgrade")),
        scope_downgrade=coerce_scope_downgrade(obj.get("scope_downgrade")),
        carried_forward=bool(obj.get("carried_forward")),
    ))
    return replace(entry, dimension=obj.get("d", dimension), violation_type=obj.get("vt"))


def judgment_to_dict(j: Judgment) -> dict:
    """Convert a Judgment to the dict format used in PrincipleEvidence lists."""
    d: dict = {"file": j.file}
    # Emit BOTH the long key (UI/report read 'violation_type', see
    # ui/src/models/violation.js and core/finding_mappings.py) AND the short
    # key the scoring tally groups by ('vt', see core/scoring/_tallies.py).
    # They carry the same value; keeping both fixes taxonomy scoring without
    # breaking any consumer.
    _optional = {"line": j.line, "end_line": j.end_line, "snippet": j.snippet,
                 "severity": j.severity, "violation_type": j.violation_type,
                 "vt": j.violation_type, "vt_raw": j.violation_type_raw,
                 "context": j.context, "scope": j.scope}
    d.update({k: v for k, v in _optional.items() if v})
    if j.req:
        d["req"] = j.req
    if j.req_refs:
        d["req_refs"] = [{"label": r.label, "url": r.url} for r in j.req_refs]
    if j.title:
        d["title"] = j.title
    if j.reason:
        d["reason"] = j.reason
    # Carry confidence forward only when it's not the default 100. Keeps the
    # PrincipleEvidence dicts compact for the common case where every finding
    # has full confidence; producers writing < 100 surface in the output.
    if j.confidence != FULL_CONFIDENCE:
        d["confidence"] = j.confidence
    # Carry the provenance-gate marker forward only when set, mirroring
    # confidence -- keeps the common (un-downgraded) finding dict compact.
    if j.provenance_downgrade:
        d["provenance_downgrade"] = True
    # Carry the scope-gate marker forward only when set, same reasoning --
    # and as the dict scope_gate.py stamps, not collapsed to a bool, so the
    # rule name that moved the finding survives this seam too.
    if j.scope_downgrade:
        d["scope_downgrade"] = j.scope_downgrade
    # Emit only when set, mirroring confidence / provenance_downgrade, so
    # the common (freshly-scanned) finding dict stays compact.
    if j.carried_forward:
        d["carried_forward"] = True
    return d


def parse_judgments(lines: Iterable[str], options: EvidenceParseOptions) -> list[Judgment]:
    """Parse JSONL lines and return enriched Judgment objects."""
    judgments: list[Judgment] = []
    req_refs_cache: dict[str, dict[str, list[dict]]] = {}
    for line in lines:
        result = parse_jsonl_line(line, on_malformed_line=options.on_malformed_line)
        if result is not None:
            j, llm_refs = result
            j = enrich_judgment(j, llm_refs, req_refs_cache, options)
            judgments.append(j)
    return judgments


def read_judgments(jsonl_file: Path, options: EvidenceParseOptions) -> list[Judgment]:
    """Read JSONL lines from a file and return enriched Judgment objects."""
    if not jsonl_file.exists():
        return []
    opener = options.open_fn or open_text
    with opener(jsonl_file) as _jf:
        return parse_judgments(_jf, options)
