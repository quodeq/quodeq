from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    job_id: str
    status: str
    command: str = ""
    started_at: str = ""
    ended_at: str | None = None
    exit_code: int | None = None
    logs: list[str] = field(default_factory=list)
    output_project: str | None = None
    output_run_id: str | None = None
    phase: str | None = None
    deadline_at: str | None = None
    current_dimension: str | None = None
    dimensions: list[str] | None = None
    error: str | None = None
    source: str = "internal"  # "internal" | "external"
    exit_reason: str | None = None
