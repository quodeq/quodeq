"""Low-level JSONL parsing for evidence judgments."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from pathlib import Path

from quodeq.core.evidence._refs import enrich_judgment
from quodeq.core.events.models import Judgment
from quodeq.core.types.req_ref import ReqRef
from quodeq.shared.utils import open_text

_logger = logging.getLogger(__name__)


def _jsonl_confidence(value: object, default: int = 100) -> int:
    """Clamp a JSONL confidence value to [0, 100]; missing/non-int → *default*."""
    if value is None:
        return default
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(100, coerced))


def parse_jsonl_line(line: str) -> tuple[Judgment, list[str] | None] | None:
    """Parse a single JSONL evidence line into a Judgment and optional LLM ref selection."""
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        _logger.warning("Skipping malformed JSONL line: %s", exc)
        return None

    practice_id = obj.get("p") or obj.get("req")
    verdict = obj.get("t")
    if not practice_id or verdict not in ("violation", "compliance"):
        return None

    pre_resolved = obj.get("req_refs")
    req_refs: list[ReqRef] = []
    if isinstance(pre_resolved, list):
        req_refs = [
            ReqRef(label=r.get("label", ""), url=r.get("url", ""))
            for r in pre_resolved if isinstance(r, dict)
        ]

    j = Judgment(
        practice_id=practice_id, verdict=verdict, dimension=obj.get("d", ""),
        file=obj.get("file", ""), line=obj.get("line", 0), end_line=obj.get("end_line"),
        snippet=obj.get("snippet", ""), severity=obj.get("severity", "medium"),
        violation_type=obj.get("vt") or None, reason=obj.get("reason", ""),
        req=obj.get("req"), title=obj.get("w") or None,
        context=obj.get("context") or None, scope=obj.get("scope") or None,
        confidence=_jsonl_confidence(obj.get("confidence")),
        req_refs=req_refs,
        provenance_downgrade=bool(obj.get("provenance_downgrade")),
    )
    return j, obj.get("refs")


def judgment_to_dict(j: Judgment) -> dict:
    """Convert a Judgment to the dict format used in PrincipleEvidence lists."""
    d: dict = {"file": j.file}
    # Emit BOTH the long key (UI/report read 'violation_type', see
    # ui/src/models/violation.js and core/finding_mappings.py) AND the short
    # key the scoring tally groups by ('vt', see core/scoring/_tallies.py).
    # They carry the same value; keeping both fixes taxonomy scoring without
    # breaking any consumer.
    _optional = {"line": j.line, "end_line": j.end_line, "snippet": j.snippet,
                 "severity": j.severity, "violation_type": j.violation_type,
                 "vt": j.violation_type,
                 "context": j.context, "scope": j.scope}
    d.update({k: v for k, v in _optional.items() if v})
    if j.req:
        d["req"] = j.req
    if j.req_refs:
        d["req_refs"] = [{"label": r.label, "url": r.url} for r in j.req_refs]
    if j.title:
        d["title"] = j.title
    if j.reason:
        d["reason"] = j.reason
    # Carry confidence forward only when it's not the default 100. Keeps the
    # PrincipleEvidence dicts compact for the common case where every finding
    # has full confidence; producers writing < 100 surface in the output.
    if j.confidence != 100:
        d["confidence"] = j.confidence
    # Carry the provenance-gate marker forward only when set, mirroring
    # confidence -- keeps the common (un-downgraded) finding dict compact.
    if j.provenance_downgrade:
        d["provenance_downgrade"] = True
    return d


def parse_judgments(lines: Iterable[str], compiled_dir: Path | None) -> list[Judgment]:
    """Parse JSONL lines and return enriched Judgment objects."""
    judgments: list[Judgment] = []
    req_refs_cache: dict[str, dict[str, list[dict]]] = {}
    for line in lines:
        result = parse_jsonl_line(line)
        if result is not None:
            j, llm_refs = result
            j = enrich_judgment(j, llm_refs, compiled_dir, req_refs_cache)
            judgments.append(j)
    return judgments


def read_judgments(
    jsonl_file: Path, compiled_dir: Path | None,
    open_fn: Callable[[Path], AbstractContextManager[Iterable[str]]] | None = None,
) -> list[Judgment]:
    """Read JSONL lines from a file and return enriched Judgment objects."""
    if not jsonl_file.exists():
        return []
    opener = open_fn or open_text
    with opener(jsonl_file) as _jf:
        return parse_judgments(_jf, compiled_dir)
