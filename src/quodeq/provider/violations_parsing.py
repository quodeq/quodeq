"""Low-level parsers for extracting violations from JSONL, evidence JSON, and stream files."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from quodeq.engine._event_text import TEXT_EXTRACTORS
from quodeq.engine.evidence_parser import _build_req_refs_lookup
from quodeq.provider.violation_context import FindingSpec, ViolationContext, build_finding_base, format_file_line


def _build_finding_entry(obj: dict, dimension: str, req_refs_lookup: dict[str, list[dict]] | None = None) -> dict[str, Any]:
    """Build a normalized finding dict from a raw JSON object."""
    req = obj.get("req")
    req_refs = req_refs_lookup.get(req) if req and req_refs_lookup else None
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
    """Count unique file paths read by the AI in a stream file."""
    files: set[str] = set()
    try:
        with open(stream_path) as _sf:
            for raw_line in _sf:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    files.update(_extract_files_from_stream_event(json.loads(stripped)))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return len(files)


def parse_violations_from_jsonl(
    jsonl_path: Path, stream_path: Path | None, ctx: ViolationContext,
    compiled_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Parse live JSONL findings written by the MCP server."""
    req_refs_lookup = _build_req_refs_lookup(compiled_dir, ctx.dimension) if compiled_dir else None
    try:
        with open(jsonl_path) as _f:
            violations, compliance = _parse_jsonl_findings(_f, ctx.dimension, req_refs_lookup)
    except OSError:
        return None
    files_read = _count_files_in_stream(stream_path) if stream_path and stream_path.exists() else 0
    return {
        "dimension": ctx.dimension,
        "runId": ctx.run_id,
        "project": ctx.project,
        "violations": violations,
        "compliance": compliance,
        "partial": True,
        "progress": {
            "filesRead": files_read,
            "violations": len(violations),
            "compliance": len(compliance),
        },
    }


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
        data = json.loads(evidence_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    violations = _extract_violations_from_principles(data.get("principles") or {})
    return {"dimension": ctx.dimension, "runId": ctx.run_id, "project": ctx.project, "violations": violations, "partial": True}


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


def _extract_files_from_stream_event(event: dict) -> set[str]:
    """Extract file paths from Read/Grep tool_use blocks in a stream event."""
    files: set[str] = set()
    etype = event.get("type", "")
    if etype == "assistant":
        blocks = event.get("message", {}).get("content", [])
    elif etype == "item.completed":
        blocks = event.get("item", {}).get("content", [])
    else:
        return files
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") in ("Read", "Grep"):
            fp = (block.get("input") or {}).get("file_path") or (block.get("input") or {}).get("path")
            if fp:
                files.add(fp)
    return files


def parse_violations_from_stream(stream_path: Path, ctx: ViolationContext) -> dict[str, Any] | None:
    """Extract violations from a live-stream event log file."""
    violations: list[dict[str, Any]] = []
    compliance: list[dict[str, Any]] = []
    seen: set[str] = set()
    files_read: set[str] = set()
    try:
        with open(stream_path) as _stream:
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
                files_read.update(_extract_files_from_stream_event(event))
    except OSError:
        return None

    return {
        "dimension": ctx.dimension,
        "runId": ctx.run_id,
        "project": ctx.project,
        "violations": violations,
        "compliance": compliance,
        "partial": True,
        "progress": {
            "filesRead": len(files_read),
            "violations": len(violations),
            "compliance": len(compliance),
        },
    }
