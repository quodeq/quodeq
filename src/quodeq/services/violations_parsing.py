"""Low-level parsers for extracting violations from JSONL, evidence JSON, and stream files."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable

from quodeq.core.types import Finding, ProgressInfo, ViolationResponse
from quodeq.engine._event_text import TEXT_EXTRACTORS
from quodeq.engine.analysis_stream import count_files_in_stream, extract_files_from_event
from quodeq.engine.evidence_parser import build_req_refs_lookup, resolve_llm_refs
from quodeq.services.violation_context import FindingSpec, ViolationContext, build_finding_base, format_file_line
from quodeq.shared.utils import open_text, read_json

_logger = logging.getLogger(__name__)

_TYPE_VIOLATION = "violation"
_TYPE_COMPLIANCE = "compliance"
_FINDING_TYPES = frozenset({_TYPE_VIOLATION, _TYPE_COMPLIANCE})


@dataclass(frozen=True)
class _ResponseOptions:
    """Keyword-only parameters for _build_violation_response."""
    partial: bool = False
    progress: dict[str, int] | None = None


def _build_violation_response(
    ctx: ViolationContext,
    violations: list[Finding],
    compliance: list[Finding],
    options: _ResponseOptions | None = None,
) -> ViolationResponse:
    """Build the common ViolationResponse for violation/compliance parse results."""
    opts = options or _ResponseOptions()
    progress: ProgressInfo | None = None
    if opts.progress is not None:
        progress = ProgressInfo(
            files_read=opts.progress.get("filesRead", 0),
            violations=opts.progress.get("violations", 0),
            compliance=opts.progress.get("compliance", 0),
        )
    return ViolationResponse(
        dimension=ctx.dimension,
        run_id=ctx.run_id,
        project=ctx.project,
        violations=violations,
        compliance=compliance,
        partial=opts.partial,
        progress=progress,
    )


def _build_finding_entry(obj: dict, dimension: str, req_refs_lookup: dict[str, list[dict]] | None = None) -> Finding:
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
        principle=obj["p"],
        file=obj.get("file"),
        line=obj.get("line"),
        title=obj.get("w"),
        reason=obj.get("reason"),
        snippet=obj.get("snippet"),
        severity=obj.get("severity"),
        cwe=obj.get("cwe"),
        req=req,
        req_refs=req_refs,
    ))
    return replace(entry, dimension=obj.get("d", dimension), violation_type=obj.get("vt"))


def _parse_jsonl_findings(
    lines: Iterable[str], dimension: str, req_refs_lookup: dict[str, list[dict]] | None = None,
) -> tuple[list[Finding], list[Finding]]:
    """Parse raw JSONL lines into deduplicated violation and compliance lists."""
    violations: list[Finding] = []
    compliance: list[Finding] = []
    seen: set[tuple] = set()
    for raw_line in lines:
        raw = raw_line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not obj.get("p") or obj.get("t") not in _FINDING_TYPES:
            continue
        dedup_key = (obj.get("p"), obj.get("t"), obj.get("file"), obj.get("line"))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        entry = _build_finding_entry(obj, dimension, req_refs_lookup)
        if obj["t"] == _TYPE_VIOLATION:
            violations.append(entry)
        else:
            compliance.append(entry)
    return violations, compliance


def _count_files_in_stream(stream_path: Path) -> int:
    """Count unique file paths read by the AI in a stream file.

    Delegates to :func:`quodeq.engine.analysis_stream.count_files_in_stream`.
    """
    return len(count_files_in_stream(stream_path))


def parse_violations_from_jsonl(
    jsonl_path: Path, stream_path: Path | None, ctx: ViolationContext,
    compiled_dir: Path | None = None,
) -> ViolationResponse | None:
    """Parse live JSONL findings written by the MCP server."""
    req_refs_lookup = build_req_refs_lookup(compiled_dir, ctx.dimension) if compiled_dir else None
    try:
        with open_text(jsonl_path) as _f:
            violations, compliance = _parse_jsonl_findings(_f, ctx.dimension, req_refs_lookup)
    except OSError as exc:
        _logger.warning("Failed to read findings file: %s", exc)
        return None
    files_read = _count_files_in_stream(stream_path) if stream_path and stream_path.exists() else 0
    return _build_violation_response(
        ctx, violations, compliance,
        _ResponseOptions(
            partial=True,
            progress={"filesRead": files_read, "violations": len(violations), "compliance": len(compliance)},
        ),
    )


def _build_violation_from_principle(violation: dict, label: str) -> Finding:
    """Build a normalized violation from a principle's violation entry."""
    return build_finding_base(FindingSpec(
        principle=label,
        file=format_file_line(violation.get("file"), violation.get("line")),
        line=violation.get("line"),
        title=violation.get("title"),
        reason=violation.get("reason"),
        snippet=violation.get("snippet"),
        severity=violation.get("severity"),
        cwe=violation.get("cwe"),
    ))


def _extract_violations_from_principles(principles: dict) -> list[Finding]:
    """Walk all principles and collect normalized violation findings."""
    violations: list[Finding] = []
    for raw_key, pdata in principles.items():
        label = pdata.get("display_name") or raw_key
        for violation in pdata.get("violations") or []:
            violations.append(_build_violation_from_principle(violation, label))
    return violations


def parse_violations_from_evidence(evidence_path: Path, ctx: ViolationContext) -> ViolationResponse | None:
    """Extract violations from a completed evidence JSON file."""
    try:
        data = read_json(evidence_path)
    except (OSError, json.JSONDecodeError):
        return None
    violations = _extract_violations_from_principles(data.get("principles") or {})
    return _build_violation_response(ctx, violations, [], _ResponseOptions(partial=True))


def _try_parse_text_line(
    stripped_line: str, dimension: str, seen: set[str],
) -> tuple[str, Finding] | None:
    """Parse a single JSON line from a text block, returning (type, entry) or None."""
    if not stripped_line.startswith("{"):
        return None
    try:
        obj = json.loads(stripped_line)
    except json.JSONDecodeError:
        return None
    if not obj.get("p") or obj.get("t") not in _FINDING_TYPES:
        return None
    key = f"{obj['p']}:{obj.get('file', '')}:{obj.get('line', '')}:{obj['t']}"
    if key in seen:
        return None
    seen.add(key)
    entry = _build_finding_entry(obj, dimension)
    if entry.snippet:
        entry = replace(entry, snippet=str(entry.snippet).splitlines()[0].strip())
    return obj["t"], entry


def _parse_entries_from_texts(
    texts: list[str], dimension: str, seen: set[str]
) -> tuple[list[Finding], list[Finding]]:
    """Parse violation/compliance entries from a list of text blocks."""
    violations: list[Finding] = []
    compliance: list[Finding] = []
    for text in texts:
        for text_line in text.splitlines():
            result = _try_parse_text_line(text_line.strip(), dimension, seen)
            if result is None:
                continue
            finding_type, entry = result
            if finding_type == _TYPE_VIOLATION:
                violations.append(entry)
            else:
                compliance.append(entry)
    return violations, compliance


@dataclass
class _StreamAccumulator:
    """Mutable accumulator for stream-line parsing results."""
    dimension: str
    violations: list[Finding] = field(default_factory=list)
    compliance: list[Finding] = field(default_factory=list)
    seen: set[str] = field(default_factory=set)
    files_read: set[str] = field(default_factory=set)


def _parse_stream_line(stripped: str, acc: _StreamAccumulator) -> None:
    """Parse one non-empty stream line, appending findings to *acc*."""
    try:
        event = json.loads(stripped)
    except json.JSONDecodeError:
        return
    extractor = TEXT_EXTRACTORS.get(event.get("type"))
    texts = extractor(event) if extractor else []
    new_v, new_c = _parse_entries_from_texts(texts, acc.dimension, acc.seen)
    acc.violations.extend(new_v)
    acc.compliance.extend(new_c)
    acc.files_read.update(extract_files_from_event(event))


def parse_violations_from_stream(stream_path: Path, ctx: ViolationContext) -> ViolationResponse | None:
    """Extract violations from a live-stream event log file."""
    acc = _StreamAccumulator(dimension=ctx.dimension)
    try:
        with open_text(stream_path) as _stream:
            for raw_line in _stream:
                stripped = raw_line.strip()
                if stripped:
                    _parse_stream_line(stripped, acc)
    except OSError as exc:
        _logger.warning("Failed to read stream file: %s", exc)
        return None

    return _build_violation_response(
        ctx, acc.violations, acc.compliance,
        _ResponseOptions(
            partial=True,
            progress={"filesRead": len(acc.files_read), "violations": len(acc.violations), "compliance": len(acc.compliance)},
        ),
    )
