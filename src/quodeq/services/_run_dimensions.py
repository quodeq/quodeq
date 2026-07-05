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
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.shared.dimensions_state import read_dimensions


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
