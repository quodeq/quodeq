"""Boundary module — re-exports adapter symbols used by service-layer code.

This module is the single point where the services layer crosses into the
adapters/data layer.  All service modules should import report-parser
types and functions from here rather than reaching directly into
``quodeq.adapters.fs.report_parser`` or ``quodeq.data.fs.report_parser``.

The ``RunStorage`` Protocol is defined here (services layer) so that
inner layers can depend on it without introducing a circular dependency.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from quodeq.core.types import DimensionResult

# --- Re-exports from the data / adapter layer ------------------------------

from quodeq.data.fs.report_parser.grades import (
    calculate_trend,
    most_frequent_grade,
    parse_numeric_score,
    summarize_dimensions,
)
from quodeq.data.fs.report_parser.runs import (
    RunInfo as RunInfo,
    list_runs,
    read_run_data,
    safe_read_dir,
)


# --- Protocol (owned by the services layer) --------------------------------

@runtime_checkable
class RunStorage(Protocol):
    """Interface for run data storage backends.

    The default filesystem implementation is provided by the module-level
    ``read_run_data`` and ``list_runs`` functions in
    ``quodeq.data.fs.report_parser.runs``.  Alternative backends (S3,
    database) should implement this protocol.
    """

    def read_run_data(self, project: str, run_id: str) -> list[DimensionResult]:
        """Load all dimension evaluations and evidence for a single run."""
        ...

    def list_runs(self, project: str, *, limit: int = 100) -> list[RunInfo]:
        """Return runs for a project, sorted newest-first by date."""
        ...


__all__ = [
    # Protocol
    "RunStorage",
    # Types
    "RunInfo",
    # Functions
    "calculate_trend",
    "list_runs",
    "most_frequent_grade",
    "parse_numeric_score",
    "read_run_data",
    "safe_read_dir",
    "summarize_dimensions",
]
