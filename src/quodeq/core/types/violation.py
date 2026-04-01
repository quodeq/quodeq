from __future__ import annotations

from dataclasses import dataclass, field

from .finding import Finding


@dataclass(frozen=True, slots=True)
class ProgressInfo:
    """Live progress counters streamed during an ongoing dimension analysis."""

    files_read: int = 0
    violation_count: int = 0
    compliance_count: int = 0


@dataclass(frozen=True, slots=True)
class ViolationResponse:
    dimension: str
    run_id: str
    project: str
    violations: list[Finding] = field(default_factory=list)
    compliance: list[Finding] = field(default_factory=list)
    partial: bool = False
    progress: ProgressInfo | None = None


@dataclass(frozen=True, slots=True)
class ViolationFileEntry:
    path: str
    count: int = 0
    critical: int = 0
    major: int = 0
    minor: int = 0


@dataclass(frozen=True, slots=True)
class ViolationSummary:
    total: int = 0
    critical: int = 0
    major: int = 0
    minor: int = 0
    files: list[ViolationFileEntry] = field(default_factory=list)
