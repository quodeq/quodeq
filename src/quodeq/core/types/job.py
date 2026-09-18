"""Read-side shape of a background evaluation job."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    """One background job frozen at the moment it was read.

    Built by ``data.mappers.parse_job_snapshot`` from the job store's wire
    dict and handed to the API and CLI. A running job's fields go stale as
    soon as the snapshot is taken; poll again rather than caching it.
    """

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
    ai_provider: str | None = None
    ai_model: str | None = None
    # Run budget in seconds. 0 = explicitly unlimited, None = unknown.
    time_limit_s: int | None = None
