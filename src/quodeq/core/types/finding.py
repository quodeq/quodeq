from __future__ import annotations

from dataclasses import dataclass, field


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
class ReqRef:
    label: str
    url: str


@dataclass(frozen=True, slots=True)
class Finding:
    principle: str | None = None
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
