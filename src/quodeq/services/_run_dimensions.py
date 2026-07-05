"""Read the dimensions a run ACTUALLY configured.

A run records the dimensions it configured in two authoritative places
under its run dir:

* ``dimensions.json`` (``{"schema_version":1, "dimensions": {...}}``) —
  the keys are the configured dimensions. Preferred.
* ``status.json`` (``{"dimensions": [...]}``) — the same list. Fallback
  for runs whose per-dim sidecar is missing.

This is the current-standard signal: a project that stopped evaluating
a dimension (e.g. ``clean-architecture``) will not list it here even
though old runs and ``evaluation.db`` drift still carry it. Scoping the
accumulated grade and the project card to this set drops those stale
dimensions.

The read is fail-open: an unreadable/absent pair returns the empty set,
and callers must treat that as "don't filter" rather than "no dims".

The current standard is the UNION of configured dimensions over the last
few ELIGIBLE runs (:func:`current_standard_dimensions`), not just the
single latest run: a targeted subset re-run (e.g. one that scans only
``maintainability``) must not collapse the standard to that one dimension.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from quodeq.shared.dimensions_state import read_dimensions

if TYPE_CHECKING:
    from quodeq.services.ports import RunInfo

# Union the configured dimensions over the last N eligible runs so a subset
# re-run doesn't collapse the standard, while dimensions retired more than N
# eligible runs ago drop out.
_STANDARD_WINDOW = 5


def configured_dimensions(run_dir: Path) -> set[str]:
    """Return the set of dimension IDs *run_dir* configured.

    Prefers ``dimensions.json`` keys; falls back to the ``dimensions``
    list in ``status.json``. Returns an empty set when neither file is
    present or parseable — callers must interpret that as "unknown, do
    not filter" (fail-open), never as "no dimensions".
    """
    dims = read_dimensions(run_dir).get("dimensions")
    if isinstance(dims, dict) and dims:
        return set(dims.keys())

    status_path = run_dir / "status.json"
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, dict):
        return set()
    status_dims = data.get("dimensions")
    if isinstance(status_dims, list):
        return {d for d in status_dims if isinstance(d, str)}
    return set()


def current_standard_dimensions(
    reports_root: Path,
    project: str,
    run_infos: list["RunInfo"],
    *,
    window: int = _STANDARD_WINDOW,
) -> set[str]:
    """Return the project's current dimension standard.

    The union of :func:`configured_dimensions` over the last *window*
    ELIGIBLE runs (newest-first). Unioning over a window means a targeted
    subset re-run (which configures only one dimension) does not collapse
    the standard, while a dimension retired more than *window* eligible
    runs ago drops out.

    Filters to eligible runs internally so the result is correct
    regardless of whether the caller pre-filtered. Returns the empty set
    when there are no eligible runs or every config is unreadable — a
    fail-open signal callers must treat as "don't filter".
    """
    from quodeq.services.dim_resolution import is_eligible_for_default_view  # noqa: PLC0415

    eligible = [r for r in run_infos if is_eligible_for_default_view(r.status)]
    standard: set[str] = set()
    for run in eligible[:window]:
        standard |= configured_dimensions(reports_root / project / run.run_id)
    return standard
