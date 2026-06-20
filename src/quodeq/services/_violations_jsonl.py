"""JSONL-specific parsing for extracting violations from MCP findings files."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from quodeq.core.types import Finding, ViolationResponse
from quodeq.core.evidence.parser import build_req_refs_lookup
from quodeq.analysis.stream.counters import count_files_in_stream
from quodeq.services.violation_context import ViolationContext
from quodeq.services.violations_parsing import (
    _build_finding_entry,
    _build_violation_response,
    _ResponseOptions,
    _FINDING_TYPES,
    _TYPE_COMPLIANCE,
    _TYPE_VIOLATION,
)
from quodeq.config.paths import default_paths
from quodeq.shared.utils import open_text
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)


def _parse_jsonl_findings(
    lines: Iterable[str], dimension: str, req_refs_lookup: dict[str, list[dict]] | None = None,
    req_to_principle: dict[str, str] | None = None,
    dismissed_keys: "set[tuple] | None" = None,
    deleted_keys: "set[tuple] | None" = None,
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
        if not isinstance(obj, dict):
            continue
        principle = obj.get("p") or obj.get("req")
        if not principle or obj.get("t") not in _FINDING_TYPES:
            continue
        # Skip dismissed findings -- match by req ID (e.g. "M-MOD-3"), not principle name
        if dismissed_keys and obj.get("t") == _TYPE_VIOLATION:
            req_id = obj.get("req") or principle
            dismissed_key = (req_id, obj.get("file", ""), obj.get("line", 0))
            if dismissed_key in dismissed_keys:
                continue
        obj["p"] = req_to_principle.get(principle, principle) if req_to_principle else principle
        # Skip permanently-deleted findings -- match by (dimension, principle, file).
        if deleted_keys and obj.get("t") == _TYPE_VIOLATION:
            deleted_key = (dimension, obj["p"], obj.get("file", ""))
            if deleted_key in deleted_keys:
                continue
        dedup_key = (principle, obj.get("t"), obj.get("file"), obj.get("line"))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        entry = _build_finding_entry(obj, dimension, req_refs_lookup)
        if obj["t"] == _TYPE_VIOLATION:
            violations.append(entry)
        else:
            compliance.append(entry)
    return violations, compliance


def _load_req_to_principle(dimension: str, evaluators_dir: "Path | None" = None) -> dict[str, str]:
    """Load req ID -> principle name mapping for custom evaluators.

    Args:
        dimension: The dimension ID to look up.
        evaluators_dir: Directory containing evaluator JSON files.
            Defaults to ``default_paths().evaluators_dir`` when not provided.
    """
    if evaluators_dir is None:
        evaluators_dir = default_paths().evaluators_dir
    if not evaluators_dir.is_dir():
        return {}
    validate_path_segment(dimension)
    path = evaluators_dir / f"{dimension}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        mapping: dict[str, str] = {}
        for p in data.get("principles", []):
            pname = p.get("name", "")
            for req in p.get("requirements", []):
                rid = req.get("id", "")
                if rid and pname:
                    mapping[rid] = pname
        return mapping
    except (OSError, ValueError):
        return {}


def parse_violations_from_jsonl(
    jsonl_path: Path, stream_path: Path | None, ctx: ViolationContext,
    compiled_dir: Path | None = None,
    dismissed_keys: "set[tuple] | None" = None,
    deleted_keys: "set[tuple] | None" = None,
) -> ViolationResponse | None:
    """Parse live JSONL findings written by the MCP server."""
    req_refs_lookup = build_req_refs_lookup(compiled_dir, ctx.dimension) if compiled_dir else None
    req_to_principle = _load_req_to_principle(ctx.dimension)
    try:
        with open_text(jsonl_path) as _f:
            violations, compliance = _parse_jsonl_findings(
                _f, ctx.dimension, req_refs_lookup, req_to_principle,
                dismissed_keys=dismissed_keys, deleted_keys=deleted_keys,
            )
    except OSError as exc:
        _logger.warning("Failed to read findings file: %s", exc)
        return None
    files_read = len(count_files_in_stream(stream_path)) if stream_path and stream_path.exists() else 0
    return _build_violation_response(
        ctx, violations, compliance,
        _ResponseOptions(
            partial=True,
            progress={"filesRead": files_read, "violations": len(violations), "compliance": len(compliance)},
        ),
    )
