"""What a model or checker reported about one finding, before any standard lookup."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


@dataclass(frozen=True, slots=True)
class FindingFacts:
    """The reported fields of a finding. Nothing here depends on the standard.

    ``principle_hint`` is the ``p`` a writer may have sent: older rows name the
    principle directly and deterministic checks put a requirement id there.
    ``admit`` only reads it when there is no ``req``.
    """

    req: str | None
    verdict: str | None
    dimension: str | None
    file: str | None
    line: int | None
    end_line: int | None = None
    snippet: str | None = None
    reason: str | None = None
    title: str | None = None
    scope: str | None = None
    severity: str | None = None
    confidence: int | None = None
    violation_type: str | None = None
    cwe: str | None = None
    principle_hint: str | None = None

    @classmethod
    def from_wire(cls, row: dict[str, Any]) -> FindingFacts:
        """The facts of a wire row (evidence JSONL, cache entry, MCP arguments).

        Derived keys already on the row (``req_refs``, a resolved ``p``) are
        read only as ``principle_hint``; they are never trusted as derived.
        """
        return cls(
            req=_text(row.get("req")),
            verdict=_text(row.get("t")),
            dimension=_text(row.get("d")),
            file=_text(row.get("file")),
            line=_int(row.get("line")),
            end_line=_int(row.get("end_line")),
            snippet=row.get("snippet"),
            reason=row.get("reason"),
            title=row.get("w"),
            scope=_text(row.get("scope")),
            severity=_text(row.get("severity")),
            confidence=_int(row.get("confidence")),
            violation_type=_text(row.get("vt_raw") or row.get("vt")),
            cwe=_text(row.get("cwe")),
            principle_hint=_text(row.get("p")),
        )
