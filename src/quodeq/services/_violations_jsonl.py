"""JSONL-specific parsing for extracting violations from MCP findings files."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from quodeq.core.types import Finding, ViolationResponse
from quodeq.core.evidence._req_mapping import PrincipleResolver, build_principle_resolver
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
    resolver: PrincipleResolver | None = None,
    dismissed_keys: "set[tuple] | None" = None,
    deleted_keys: "set[tuple] | None" = None,
) -> tuple[list[Finding], list[Finding]]:
    """Parse raw JSONL lines into deduplicated violation and compliance lists.

    When *resolver* is supplied, findings whose principle is not in the
    dimension's standard are skipped -- the same quarantine the report path
    applies in ``_group_judgments``, so this live view cannot show more
    findings than the persisted evaluation.
    """
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
        if resolver is not None:
            resolved = resolver.resolve(principle)
            if resolved is None:
                continue
            obj["p"] = resolved
        else:
            obj["p"] = principle
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


def _build_resolver(dimension: str, compiled_dir: Path | None) -> PrincipleResolver:
    """Resolve *dimension*'s principle set the same way the report path does.

    Routes through the shared builder in ``core.evidence._req_mapping`` rather
    than reading evaluators here, so this path inherits the compiled-standard
    fallback. Without it the map is empty on a stock install (the evaluators
    dir exists but is empty for built-in dimensions) and every requirement ID
    would look unmappable.
    """
    validate_path_segment(dimension)  # dimension reaches a path join downstream
    return build_principle_resolver(
        dimension, default_paths().evaluators_dir, compiled_dir,
    )


def parse_violations_from_jsonl(
    jsonl_path: Path, stream_path: Path | None, ctx: ViolationContext,
    compiled_dir: Path | None = None,
    dismissed_keys: "set[tuple] | None" = None,
    deleted_keys: "set[tuple] | None" = None,
) -> ViolationResponse | None:
    """Parse live JSONL findings written by the MCP server."""
    req_refs_lookup = build_req_refs_lookup(compiled_dir, ctx.dimension) if compiled_dir else None
    resolver = _build_resolver(ctx.dimension, compiled_dir)
    try:
        with open_text(jsonl_path) as _f:
            violations, compliance = _parse_jsonl_findings(
                _f, ctx.dimension, req_refs_lookup, resolver,
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
