"""Low-level parsers for extracting violations from JSONL, evidence JSON, and stream files."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from quodeq.engine._event_text import TEXT_EXTRACTORS
from quodeq.engine.analysis_stream import count_files_in_stream, extract_files_from_event
from quodeq.engine.evidence_parser import build_req_refs_lookup, resolve_llm_refs
from quodeq.provider.violation_context import FindingSpec, ViolationContext, build_finding_base, format_file_line

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ResponseOptions:
    """Keyword-only parameters for _build_violation_response."""
    partial: bool = False
    progress: dict[str, int] | None = None


def _build_violation_response(
    ctx: ViolationContext,
    violations: list[dict[str, Any]],
    compliance: list[dict[str, Any]],
    options: _ResponseOptions | None = None,
) -> dict[str, Any]:
    """Build the common response dict for violation/compliance parse results."""
    opts = options or _ResponseOptions()
    result: dict[str, Any] = {
        "dimension": ctx.dimension,
        "runId": ctx.run_id,
        "project": ctx.project,
        "violations": violations,
        "compliance": compliance,
        "partial": opts.partial,
    }
    if opts.progress is not None:
        result["progress"] = opts.progress
    return result


def _build_finding_entry(obj: dict, dimension: str, req_refs_lookup: dict[str, list[dict]] | None = None) -> dict[str, Any]:
    """Build a normalized finding dict from a raw JSON object."""
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
    entry["dimension"] = obj.get("d", dimension)
    entry["violationType"] = obj.get("vt")
    return entry


def _parse_jsonl_findings(
    lines: Iterable[str], dimension: str, req_refs_lookup: dict[str, list[dict]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse raw JSONL lines into deduplicated violation and compliance lists."""
    violations: list[dict[str, Any]] = []
    compliance: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for raw_line in lines:
        raw = raw_line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not obj.get("p") or obj.get("t") not in ("violation", "compliance"):
            continue
        dedup_key = (obj.get("p"), obj.get("t"), obj.get("file"), obj.get("line"))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        entry = _build_finding_entry(obj, dimension, req_refs_lookup)
        if obj["t"] == "violation":
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
) -> dict[str, Any] | None:
    """Parse live JSONL findings written by the MCP server."""
    req_refs_lookup = build_req_refs_lookup(compiled_dir, ctx.dimension) if compiled_dir else None
    try:
        with open(jsonl_path, encoding="utf-8") as _f:
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


def _build_violation_from_principle(violation: dict, label: str) -> dict[str, Any]:
    """Build a normalized violation dict from a principle's violation entry."""
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


def _extract_violations_from_principles(principles: dict) -> list[dict[str, Any]]:
    """Walk all principles and collect normalized violation dicts."""
    violations: list[dict[str, Any]] = []
    for raw_key, pdata in principles.items():
        label = pdata.get("display_name") or raw_key
        for violation in pdata.get("violations") or []:
            violations.append(_build_violation_from_principle(violation, label))
    return violations


def parse_violations_from_evidence(evidence_path: Path, ctx: ViolationContext) -> dict[str, Any] | None:
    """Extract violations from a completed evidence JSON file."""
    try:
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    violations = _extract_violations_from_principles(data.get("principles") or {})
    return _build_violation_response(ctx, violations, [], _ResponseOptions(partial=True))


def _parse_entries_from_texts(
    texts: list[str], dimension: str, seen: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse violation/compliance entries from a list of text blocks."""
    violations: list[dict[str, Any]] = []
    compliance: list[dict[str, Any]] = []
    for text in texts:
        for text_line in text.splitlines():
            stripped_line = text_line.strip()
            if not stripped_line.startswith("{"):
                continue
            try:
                obj = json.loads(stripped_line)
            except json.JSONDecodeError:
                continue
            if not obj.get("p") or obj.get("t") not in ("violation", "compliance"):
                continue
            key = f"{obj['p']}:{obj.get('file', '')}:{obj.get('line', '')}:{obj['t']}"
            if key in seen:
                continue
            seen.add(key)
            entry = _build_finding_entry(obj, dimension)
            snippet = entry.get("snippet")
            if snippet:
                entry["snippet"] = str(snippet).splitlines()[0].strip()
            if obj["t"] == "violation":
                violations.append(entry)
            else:
                compliance.append(entry)
    return violations, compliance


def parse_violations_from_stream(stream_path: Path, ctx: ViolationContext) -> dict[str, Any] | None:
    """Extract violations from a live-stream event log file."""
    violations: list[dict[str, Any]] = []
    compliance: list[dict[str, Any]] = []
    seen: set[str] = set()
    files_read: set[str] = set()
    try:
        with open(stream_path, encoding="utf-8") as _stream:
            for raw_line in _stream:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    event = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                extractor = TEXT_EXTRACTORS.get(event.get("type"))
                texts = extractor(event) if extractor else []
                new_v, new_c = _parse_entries_from_texts(texts, ctx.dimension, seen)
                violations.extend(new_v)
                compliance.extend(new_c)
                files_read.update(extract_files_from_event(event))
    except OSError as exc:
        _logger.warning("Failed to read stream file: %s", exc)
        return None

    return _build_violation_response(
        ctx, violations, compliance,
        _ResponseOptions(
            partial=True,
            progress={"filesRead": len(files_read), "violations": len(violations), "compliance": len(compliance)},
        ),
    )
