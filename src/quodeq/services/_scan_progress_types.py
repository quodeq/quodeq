"""Data shapes for live scan progress.

Split from ``scan_progress.py`` (into its own module rather than folded into
``_scan_progress_dims.py``) so both that module and the ``scan_progress.py``
facade can import them without a cycle.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class _DimProgress:
    id: str
    state: str  # "done" | "running" | "pending"
    files: dict
    violations: int = 0
    compliance: int = 0
    duplicates: int = 0
    suppressed: int = 0  # re-found findings already dismissed/deleted in the dashboard
    quarantined: int = 0  # findings whose principle is not in the dimension's standard
    elapsed_s: float | None = None
    active_agents: int = 0
    estimate_reason: str | None = None  # see _dim_estimates module docstring
    exit_reason: str | None = None
    files_cached: int | None = None        # files already analyzed in previous runs
    files_project_total: int | None = None  # all dispatchable source files for this dim
    files_excluded: int | None = None       # files the provider can never dispatch (size cap)


@dataclass
class _ScanProgress:
    job_id: str
    state: str
    phase: str | None
    current_dimension: str | None
    project_files: int
    total_elapsed_s: float | None
    # The time limit is one deadline for the whole run, shared across all
    # selected dimensions — never a per-dimension allowance.
    budget_s: int | None = None
    # Run-level exit_reason from status.json (e.g. "provider_fatal",
    # "failure_streak"). Lets the UI say WHY a failed run stopped instead of
    # only that it did.
    exit_reason: str | None = None
    dimensions: list[_DimProgress] = field(default_factory=list)
