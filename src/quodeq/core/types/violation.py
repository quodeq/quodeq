from __future__ import annotations

from dataclasses import dataclass, field

from .finding import Finding

# Bumped when the persisted shape of ViolationResponse/ViolationSummary
# changes in a way a reader needs to know about. Follows the schema_version
# convention used elsewhere for persisted JSON (see e.g.
# quodeq.core.run.state.SCHEMA_VERSION). Defaulted so old on-disk payloads
# that predate this field still deserialize.
VIOLATION_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ProgressInfo:
    """Live progress counters streamed during an ongoing dimension analysis."""

    files_read: int = 0
    violation_count: int = 0
    compliance_count: int = 0


@dataclass(frozen=True, slots=True)
class ViolationResponse:
    """Result of a dimension analysis containing violations and compliance findings."""

    dimension: str
    run_id: str
    project: str
    violations: list[Finding] = field(default_factory=list)
    compliance: list[Finding] = field(default_factory=list)
    partial: bool = False
    progress: ProgressInfo | None = None
    schema_version: int = VIOLATION_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class ViolationFileEntry:
    """Per-file violation counts grouped by severity."""

    path: str
    count: int = 0
    critical: int = 0
    major: int = 0
    minor: int = 0


@dataclass(frozen=True, slots=True)
class ViolationSummary:
    """Aggregate violation totals across all analysed files."""

    total: int = 0
    critical: int = 0
    major: int = 0
    minor: int = 0
    files: list[ViolationFileEntry] = field(default_factory=list)
    schema_version: int = VIOLATION_SCHEMA_VERSION
