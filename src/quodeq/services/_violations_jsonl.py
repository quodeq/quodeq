"""JSONL-specific parsing for extracting violations from MCP findings files."""
from __future__ import annotations

import logging
from pathlib import Path
from collections.abc import Callable, Iterable

from quodeq.core.types import Finding, ViolationResponse
from quodeq.core.evidence.req_mapping import PrincipleResolver, build_principle_resolver
from quodeq.core.stream.events import extract_files_from_event, parse_stream_event
from quodeq.services import live_jsonl_fold
from quodeq.services.wiring import (
    build_req_refs_lookup, decode_jsonl_objects, read_req_to_principle_map,
)
from quodeq.services.violation_context import ViolationContext
from quodeq.services.suppression import SuppressionMatcher, load_req_to_principle
from quodeq.services.suppression_keys import SuppressionKeys
from quodeq.config.paths import default_paths
from quodeq.shared.validation import validate_path_segment
from quodeq.services._violations_shared import (
    build_finding_entry,
    build_violation_response,
    ResponseOptions,
)
from quodeq.core.types.finding_type import FINDING_TYPES, FindingType

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
    identity = obj.get("req") or obj.get("p")
    if not identity or obj.get("t") not in FINDING_TYPES:
        return None
    if matcher.is_suppressed(obj):
        return None
    if resolver is None:
        obj["p"] = matcher.principle_for(obj.get("p") or identity, req=obj.get("req"))
    else:
        resolved = resolver.place(obj.get("req"), obj.get("p"))
        if resolved is None:
            return None
        obj["p"] = resolved
    # Same identity as every other dedup: the requirement, else the principle.
    dedup_key = (identity, obj.get("t"), obj.get("file"), obj.get("line"))
    if dedup_key in seen:
        return None
    seen.add(dedup_key)
    return obj


def _jsonl_parser(
    dimension: str, req_refs_lookup: dict[str, list[dict]] | None,
    resolver: PrincipleResolver | None, keys: SuppressionKeys | None,
) -> Callable[[Iterable[str]], tuple[list[Finding], list[Finding]]]:
    """Parse raw JSONL lines into deduplicated violation and compliance lists.

    Two exclusions keep this live view from showing more findings than the
    persisted evaluation: rows the dashboard suppresses (the dismissed/deleted
    sets in *keys*), and rows whose principle is not in the dimension's
    standard, which the report path quarantines in ``group_judgments``. The
    returned parser dedups across every batch it is given, so a live fold
    can feed it only the lines appended since its last call.
    """
    seen: set[tuple] = set()
    # One seam for both suppression stores, shared with the live-progress
    # tally -- see quodeq.services.suppression for the key shapes.
    matcher = SuppressionMatcher(
        dimension=dimension,
        # Hand the DismissedKeys over whole. Wrapping it in frozenset() iterated
        # it into a set of DismissedEntry objects, which is neither a
        # DismissedKeys nor the legacy {(req, file, line)} form: as_dismissed_keys
        # then tried to unpack each entry as a 3-tuple and raised TypeError. That
        # made this whole live view 500 for any project with a dismissal, which
        # is every project with a triage history.
        dismissed=(keys.dismissed or frozenset()) if keys else frozenset(),
        deleted=frozenset(keys.deleted or ()) if keys else frozenset(),
        # Same table the quarantine check uses, so the delete key and the
        # scored report can never map a req ID to different principles.
        req_to_principle=resolver.req_to_principle if resolver else {},
    )

    def _warn_malformed(raw: str) -> None:
        _logger.warning("Skipping malformed JSONL line in findings file: %s", raw[:200])

    def _warn_non_object(raw: str) -> None:
        _logger.warning("Skipping non-object JSONL row in findings file: %s", raw[:200])

    def parse(lines: Iterable[str]) -> tuple[list[Finding], list[Finding]]:
        violations: list[Finding] = []
        compliance: list[Finding] = []
        for obj in decode_jsonl_objects(
            lines, on_malformed_line=_warn_malformed, on_non_object=_warn_non_object,
        ):
            resolved_obj = _resolve_and_dedupe(obj, matcher, resolver, seen)
            if resolved_obj is None:
                continue
            entry = build_finding_entry(resolved_obj, dimension, req_refs_lookup)
            if resolved_obj["t"] == FindingType.VIOLATION:
                violations.append(entry)
            else:
                compliance.append(entry)
        return violations, compliance

    return parse


# Moved to quodeq.services.suppression, which owns the req -> principle map
# because the delete key is built from it. Kept as an alias: several tests and
# call sites still reach for the private name.
_load_req_to_principle = load_req_to_principle


def _build_resolver(
    dimension: str, compiled_dir: Path | None, evaluators_dir: Path | None = None,
) -> PrincipleResolver:
    """Resolve *dimension*'s principle set the same way the report path does.

    Routes through the shared builder in ``core.evidence._req_mapping`` rather
    than reading evaluators here, so this path inherits the compiled-standard
    fallback. Without it the map is empty on a stock install (the evaluators
    dir exists but is empty for built-in dimensions) and every requirement ID
    would look unmappable. *evaluators_dir* defaults to ``default_paths()``'s,
    resolved at call time so a caller can inject a different one for testing.
    """
    validate_path_segment(dimension)  # dimension reaches a path join downstream
    _evaluators_dir = evaluators_dir if evaluators_dir is not None else default_paths().evaluators_dir
    return build_principle_resolver(
        dimension, _evaluators_dir, compiled_dir,
        req_map_reader=read_req_to_principle_map,
    )


def parse_violations_from_jsonl(
    jsonl_path: Path, stream_path: Path | None, ctx: ViolationContext,
    compiled_dir: Path | None = None,
    keys: SuppressionKeys | None = None,
    evaluators_dir: Path | None = None,
) -> ViolationResponse | None:
    """Parse live JSONL findings written by the MCP server.

    Folded incrementally (``live_jsonl_fold``): a poll parses only the lines
    appended since the previous one, and rebuilds when the suppressions or
    the standards directories change.
    """
    identity = (
        ctx.dimension, compiled_dir, evaluators_dir,
        keys.dismissed if keys else None, frozenset(keys.deleted or ()) if keys else None,
    )

    def new_parser():
        req_refs_lookup = build_req_refs_lookup(compiled_dir, ctx.dimension) if compiled_dir else None
        resolver = _build_resolver(ctx.dimension, compiled_dir, evaluators_dir)
        return _jsonl_parser(ctx.dimension, req_refs_lookup, resolver, keys)

    if not jsonl_path.is_file():
        _logger.warning("Failed to read findings file: %s", jsonl_path)
        return None
    fold = live_jsonl_fold.fold_for(jsonl_path, identity, new_parser)
    with fold.lock:
        fold.advance()
        violations, compliance = list(fold.violations), list(fold.compliance)
    files_read = (
        live_jsonl_fold.stream_files_count(stream_path, _files_in_stream_line)
        if stream_path and stream_path.exists() else 0
    )
    return build_violation_response(
        ctx, violations, compliance,
        ResponseOptions(
            partial=True,
            progress={"filesRead": files_read, "violations": len(violations), "compliance": len(compliance)},
        ),
    )


def _files_in_stream_line(line: str) -> Iterable[str]:
    data = parse_stream_event(line)
    return extract_files_from_event(data) if data is not None else ()
