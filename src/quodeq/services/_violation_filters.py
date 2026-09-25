"""Suppression filters over parsed violation dicts (eval JSON / markdown results).

Dismissals go through the shared ``is_dismissed`` predicate (snippet
fingerprint, ``req || principle`` fallback) rather than a hand-built key, so
this view agrees with every other suppression surface. Deletions match on
``(dimension, principle, file)``.
"""
from __future__ import annotations

from typing import Any

from quodeq.core.dismissals import DismissedKeys
from quodeq.core.finding_identity import coerce_line
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.types import ViolationResponse
from quodeq.services.suppression_keys import FindingRef, is_dismissed


def violation_location(v: dict, *, log: LogSink = NULL_LOG) -> tuple[str, int]:
    """``(file, line)`` of a violation dict.

    Handles two formats:
    - Separated: file="path/to/file.py", line=42
    - Combined: file="path/to/file.py:42", line=None
    """
    raw_file = v.get("file") or ""
    line = v.get("line")
    if line is not None:
        return (raw_file, coerce_line(line))
    # Parse line from "file:line" format
    if ":" in raw_file:
        parts = raw_file.rsplit(":", 1)
        try:
            return (parts[0], int(parts[1]))
        except (ValueError, IndexError) as exc:
            log.debug(f"violation line could not be parsed for its dismissal key: {exc}")
    return (raw_file, 0)


def _violation_dismissed(
    v: dict, dismissed: "DismissedKeys | set[tuple]", principle: str | None,
) -> bool:
    """The shared predicate on a violation dict (snippet-aware, ``req || principle``)."""
    file, line = violation_location(v)
    return is_dismissed(dismissed, FindingRef(
        req=v.get("req"),
        principle=principle or v.get("practiceId") or v.get("principle"),
        file=file, line=line, snippet=v.get("snippet"),
    ))


def deleted_key_for_violation(v: dict, dimension: str, principle: str | None = None) -> tuple:
    """Build a (dimension, principle, file) suppression key from a violation dict.

    Parsed eval violations are camelCase (``practiceId``); ``principle`` is
    kept as a fallback for pre-camelCase dicts. Principle-group entries carry
    no principle field at all, so callers pass the group name as *principle*.
    """
    raw_file = v.get("file") or ""
    if v.get("line") is None and ":" in raw_file:
        raw_file = raw_file.rsplit(":", 1)[0]
    if principle is None:
        principle = v.get("practiceId") or v.get("principle") or ""
    return (dimension or "", principle or "", raw_file)


def filter_dismissed_from_result(
    result: "ViolationResponse | dict[str, Any] | None",
    dkeys: "DismissedKeys | set[tuple]",
    delkeys: "set[tuple] | None" = None,
    dimension: str = "",
) -> "ViolationResponse | dict[str, Any] | None":
    """Remove dismissed and permanently-deleted violations from any result format."""
    if not result or (not dkeys and not delkeys):
        return result
    if isinstance(result, dict):
        if "violations" in result:
            result["violations"] = [
                v for v in result["violations"]
                if not _violation_dismissed(v, dkeys, None)
                and (not delkeys or deleted_key_for_violation(v, dimension) not in delkeys)
            ]
        for p in result.get("principles", []):
            if "violations" in p:
                group_principle = p.get("name", "") or ""
                p["violations"] = [
                    v for v in p["violations"]
                    if not _violation_dismissed(v, dkeys, group_principle)
                    and (not delkeys or deleted_key_for_violation(v, dimension, group_principle) not in delkeys)
                ]
    return result
