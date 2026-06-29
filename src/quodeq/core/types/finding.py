from __future__ import annotations

from dataclasses import dataclass, field

from quodeq.core.types.req_ref import ReqRef as ReqRef


@dataclass(frozen=True, slots=True)
class SeverityTally:
    critical: int = 0
    major: int = 0
    minor: int = 0
    unknown: int = 0


@dataclass(frozen=True, slots=True)
class Totals:
    violation_count: int = 0
    compliance_count: int = 0
    severity: SeverityTally = field(default_factory=SeverityTally)


@dataclass(frozen=True, slots=True)
class Finding:
    practice_id: str | None = None
    verdict: str | None = None  # "violation" | "compliance" | "dismissed"
    file: str | None = None
    line: int | str | None = None
    end_line: int | str | None = None
    title: str | None = None
    reason: str | None = None
    snippet: str | None = None
    severity: str = "minor"
    cwe: int | str | None = None
    req: str | None = None
    req_refs: list[ReqRef] = field(default_factory=list)
    context: str | None = None
    dimension: str | None = None
    violation_type: str | None = None
    scope: str | None = None
    # 0..100. Default 100 means "scanner is fully sure this is real".
    # Lower values flag noise (path role, project shape, precedent) the
    # context-enricher pipeline downweights post-LLM.
    confidence: int = 100
    # True when the deterministic provenance gate (#639) de-escalated this
    # finding from critical to major. Audit marker surfaced in the DB/UI (#656).
    provenance_downgrade: bool = False
