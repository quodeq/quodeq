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
from quodeq.services.suppression import SuppressionMatcher, load_req_to_principle
from quodeq.services.violations_parsing import (
    _build_finding_entry,
    _build_violation_response,
    _ResponseOptions,
    _FINDING_TYPES,
    _TYPE_COMPLIANCE,
    _TYPE_VIOLATION,
)
from quodeq.shared.utils import open_text

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
    # One seam for both suppression stores, shared with the live-progress
    # tally -- see quodeq.services.suppression for the key shapes.
    matcher = SuppressionMatcher(
        dimension=dimension,
        dismissed=frozenset(dismissed_keys or ()),
        deleted=frozenset(deleted_keys or ()),
        req_to_principle=req_to_principle or {},
    )
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
        if matcher.is_suppressed(obj):
            continue
        obj["p"] = matcher.principle_for(principle)
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


# Moved to quodeq.services.suppression, which owns the req -> principle map
# because the delete key is built from it. Kept as an alias: several tests and
# call sites still reach for the private name.
_load_req_to_principle = load_req_to_principle


def parse_violations_from_jsonl(
    jsonl_path: Path, stream_path: Path | None, ctx: ViolationContext,
    compiled_dir: Path | None = None,
    dismissed_keys: "set[tuple] | None" = None,
    deleted_keys: "set[tuple] | None" = None,
) -> ViolationResponse | None:
    """Parse live JSONL findings written by the MCP server."""
    req_refs_lookup = build_req_refs_lookup(compiled_dir, ctx.dimension) if compiled_dir else None
    req_to_principle = load_req_to_principle(ctx.dimension)
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
