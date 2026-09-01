"""JSONL-specific parsing for extracting violations from MCP findings files."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from quodeq.core.types import Finding, ViolationResponse
from quodeq.core.evidence._req_mapping import PrincipleResolver, build_principle_resolver
from quodeq.data.fs.standards_loader import build_req_refs_lookup, read_req_to_principle_map
from quodeq.data.fs.stream_files import count_files_in_stream
from quodeq.services.violation_context import ViolationContext
from quodeq.services.suppression import SuppressionMatcher, load_req_to_principle
from quodeq.config.paths import default_paths
from quodeq.shared.validation import validate_path_segment
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


def _resolve_and_dedupe(
    obj: dict, matcher: SuppressionMatcher, resolver: PrincipleResolver | None, seen: "set[tuple]",
) -> dict | None:
    """Resolve *obj*'s principle, checking suppression and dedup.

    Returns the (mutated, resolved-principle) obj to keep, or None when the
    row should be dropped: not a finding-type row, suppressed
    (dismissed/deleted), unmappable to the dimension's standard (the report
    path quarantines it, so this live view must not show it either), or
    already seen.
    """
    principle = obj.get("p") or obj.get("req")
    if not principle or obj.get("t") not in _FINDING_TYPES:
        return None
    if matcher.is_suppressed(obj):
        return None
    if resolver is None:
        obj["p"] = matcher.principle_for(principle)
    else:
        resolved = resolver.resolve(principle)
        if resolved is None:
            return None
        obj["p"] = resolved
    dedup_key = (principle, obj.get("t"), obj.get("file"), obj.get("line"))
    if dedup_key in seen:
        return None
    seen.add(dedup_key)
    return obj


def _parse_jsonl_findings(
    lines: Iterable[str], dimension: str, req_refs_lookup: dict[str, list[dict]] | None = None,
    resolver: PrincipleResolver | None = None,
    dismissed_keys: "set[tuple] | None" = None,
    deleted_keys: "set[tuple] | None" = None,
) -> tuple[list[Finding], list[Finding]]:
    """Parse raw JSONL lines into deduplicated violation and compliance lists.

    Two exclusions keep this live view from showing more findings than the
    persisted evaluation: rows the dashboard suppresses (dismissed/deleted), and
    rows whose principle is not in the dimension's standard, which the report
    path quarantines in ``_group_judgments``.
    """
    violations: list[Finding] = []
    compliance: list[Finding] = []
    seen: set[tuple] = set()
    # One seam for both suppression stores, shared with the live-progress
    # tally -- see quodeq.services.suppression for the key shapes.
    matcher = SuppressionMatcher(
        dimension=dimension,
        dismissed=frozenset(dismissed_keys or ()),
        deleted=frozenset(deleted_keys or ()),
        # Same table the quarantine check uses, so the delete key and the
        # scored report can never map a req ID to different principles.
        req_to_principle=resolver.req_to_principle if resolver else {},
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
        resolved_obj = _resolve_and_dedupe(obj, matcher, resolver, seen)
        if resolved_obj is None:
            continue
        entry = _build_finding_entry(resolved_obj, dimension, req_refs_lookup)
        if resolved_obj["t"] == _TYPE_VIOLATION:
            violations.append(entry)
        else:
            compliance.append(entry)
    return violations, compliance


# Moved to quodeq.services.suppression, which owns the req -> principle map
# because the delete key is built from it. Kept as an alias: several tests and
# call sites still reach for the private name.
_load_req_to_principle = load_req_to_principle


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
        req_map_reader=read_req_to_principle_map,
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
