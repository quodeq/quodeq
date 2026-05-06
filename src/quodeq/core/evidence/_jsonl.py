"""Low-level JSONL parsing for evidence judgments."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from pathlib import Path

from quodeq.core.evidence._refs import enrich_judgment
from quodeq.core.evidence.model import Judgment
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

    j = Judgment(
        practice_id=practice_id, verdict=verdict, dimension=obj.get("d", ""),
        file=obj.get("file", ""), line=obj.get("line", 0), end_line=obj.get("end_line", 0),
        snippet=obj.get("snippet", ""), severity=obj.get("severity", "medium"),
        violation_type=obj.get("vt", ""), reason=obj.get("reason", ""),
        req=obj.get("req"), title=obj.get("w", ""),
        context=obj.get("context", ""), scope=obj.get("scope", ""),
        confidence=_jsonl_confidence(obj.get("confidence")),
    )
    pre_resolved = obj.get("req_refs")
    if isinstance(pre_resolved, list) and pre_resolved:
        j.req_refs = pre_resolved
    return j, obj.get("refs")


def judgment_to_dict(j: Judgment) -> dict:
    """Convert a Judgment to the dict format used in PrincipleEvidence lists."""
    d: dict = {"file": j.file}
    _optional = {"line": j.line, "end_line": j.end_line, "snippet": j.snippet,
                 "severity": j.severity, "violation_type": j.violation_type,
                 "context": j.context, "scope": j.scope}
    d.update({k: v for k, v in _optional.items() if v})
    for key in ("req", "req_refs", "title", "reason"):
        val = getattr(j, key, None)
        if val:
            d[key] = val
    # Carry confidence forward only when it's not the default 100. Keeps the
    # PrincipleEvidence dicts compact for the common case where every finding
    # has full confidence; producers writing < 100 surface in the output.
    confidence = getattr(j, "confidence", 100)
    if confidence != 100:
        d["confidence"] = confidence
    return d


def parse_judgments(lines: Iterable[str], compiled_dir: Path | None) -> list[Judgment]:
    """Parse JSONL lines and return enriched Judgment objects."""
    judgments: list[Judgment] = []
    req_refs_cache: dict[str, dict[str, list[dict]]] = {}
    for line in lines:
        result = parse_jsonl_line(line)
        if result is not None:
            j, llm_refs = result
            enrich_judgment(j, llm_refs, compiled_dir, req_refs_cache)
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
