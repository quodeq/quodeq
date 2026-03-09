from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


def parse_violations_from_jsonl(jsonl_path: Path, stream_path: Path | None, project: str, run_id: str, dimension: str) -> dict[str, Any] | None:
    """Parse live JSONL findings written by the MCP server."""
    try:
        lines = jsonl_path.read_text().splitlines()
    except OSError:
        return None
    violations: list[dict[str, Any]] = []
    compliance: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for raw in lines:
        raw = raw.strip()
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
        entry = {
            "principle": obj["p"],
            "dimension": obj.get("d", dimension),
            "file": obj.get("file"),
            "line": obj.get("line"),
            "title": obj.get("w"),
            "reason": obj.get("reason"),
            "snippet": obj.get("snippet"),
            "severity": obj.get("severity") or "minor",
            "cwe": obj.get("cwe"),
            "violationType": obj.get("vt"),
        }
        if obj["t"] == "violation":
            violations.append(entry)
        else:
            compliance.append(entry)
    files_read = _count_files_read(stream_path.read_text()) if stream_path and stream_path.exists() else 0
    return {
        "dimension": dimension,
        "runId": run_id,
        "project": project,
        "violations": violations,
        "compliance": compliance,
        "partial": True,
        "progress": {
            "filesRead": files_read,
            "violations": len(violations),
            "compliance": len(compliance),
        },
    }


def parse_violations_from_evidence(evidence_path: Path, project: str, run_id: str, dimension: str) -> dict[str, Any] | None:
    try:
        data = json.loads(evidence_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    violations = []
    for raw_key, pdata in (data.get("principles") or {}).items():
        label = pdata.get("display_name") or raw_key
        for violation in pdata.get("violations") or []:
            file_path = violation.get("file")
            line = violation.get("line")
            v = {
                "principle": label,
                "file": f"{file_path}:{line}" if file_path and line else file_path,
                "line": line,
                "title": violation.get("title"),
                "reason": violation.get("reason"),
                "snippet": violation.get("snippet"),
                "severity": violation.get("severity") or "minor",
            }
            if violation.get("cwe"):
                v["cwe"] = violation["cwe"]
            violations.append(v)
    return {"dimension": dimension, "runId": run_id, "project": project, "violations": violations, "partial": True}


def _texts_from_assistant(event: dict) -> list[str]:
    texts: list[str] = []
    for block in (event.get("message") or {}).get("content") or []:
        if block.get("type") == "text" and block.get("text"):
            texts.append(block["text"])
    return texts


def _texts_from_result(event: dict) -> list[str]:
    r = event.get("result")
    return [r] if r else []


def _texts_from_item_completed(event: dict) -> list[str]:
    texts: list[str] = []
    item = event.get("item") or {}
    if item.get("type") == "agent_message":
        if item.get("text"):
            texts.append(item["text"])
        for block in item.get("content") or []:
            if block.get("type") in ("text", "output_text") and block.get("text"):
                texts.append(block["text"])
    return texts


_TEXT_EXTRACTORS: dict[str, Callable] = {
    "assistant": _texts_from_assistant,
    "result": _texts_from_result,
    "item.completed": _texts_from_item_completed,
}


def _count_files_read(content: str) -> int:
    """Count unique files read by the AI from tool_use events in the stream."""
    files: set[str] = set()
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        etype = event.get("type", "")
        if etype == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_use" and block.get("name") in ("Read", "Grep"):
                    fp = (block.get("input") or {}).get("file_path") or (block.get("input") or {}).get("path")
                    if fp:
                        files.add(fp)
    return len(files)


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
            snippet = obj.get("snippet")
            entry = {
                "principle": obj["p"],
                "dimension": obj.get("d", dimension),
                "file": obj.get("file"),
                "line": obj.get("line"),
                "reason": obj.get("reason"),
                "snippet": str(snippet).splitlines()[0].strip() if snippet else None,
                "severity": obj.get("severity") or "minor",
                "cwe": obj.get("cwe"),
                "violationType": obj.get("vt"),
            }
            if obj["t"] == "violation":
                violations.append(entry)
            else:
                compliance.append(entry)
    return violations, compliance


def parse_violations_from_stream(stream_path: Path, project: str, run_id: str, dimension: str) -> dict[str, Any] | None:
    try:
        content = stream_path.read_text()
    except OSError:
        return None
    violations: list[dict[str, Any]] = []
    compliance: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        extractor = _TEXT_EXTRACTORS.get(event.get("type"))
        texts = extractor(event) if extractor else []
        new_v, new_c = _parse_entries_from_texts(texts, dimension, seen)
        violations.extend(new_v)
        compliance.extend(new_c)

    files_read = _count_files_read(content)
    return {
        "dimension": dimension,
        "runId": run_id,
        "project": project,
        "violations": violations,
        "compliance": compliance,
        "partial": True,
        "progress": {
            "filesRead": files_read,
            "violations": len(violations),
            "compliance": len(compliance),
        },
    }
