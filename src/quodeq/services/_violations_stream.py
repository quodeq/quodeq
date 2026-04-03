"""Stream-specific parsing for extracting violations from live event log files."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path

from quodeq.core.types import Finding, ViolationResponse
from quodeq.analysis.stream.event_text import TEXT_EXTRACTORS
from quodeq.analysis.stream.counters import extract_files_from_event
from quodeq.services.violation_context import ViolationContext
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
        entry = replace(entry, snippet=str(entry.snippet).strip())
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
