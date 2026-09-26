"""The since-baseline summary the dashboard shows above the numbers.

A reduction of the run diff per dimension: the baseline chosen, the majors
delta, the requirement types closed and opened, and the scoped new / resolved
counts. The finding lists stay on the diff route.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.services.run_diff import diff_runs

_SUMMARY_KEYS = ("scope", "changedFiles", "counts")


def _reduce(entry: dict[str, Any]) -> dict[str, Any]:
    since = entry.get("sinceBaseline") or {}
    types = entry.get("types") or {}
    return {
        "againstRunId": entry.get("againstRunId"),
        "againstCommitSha": entry.get("againstCommitSha"),
        "majorsDelta": entry.get("majorsDelta"),
        "types": {"closed": types.get("closed") or [], "opened": types.get("opened") or []},
        "sinceBaseline": {key: since.get(key) for key in _SUMMARY_KEYS},
    }


def since_baseline_summary(reports_root: Path, project: str, run_id: str) -> dict[str, Any]:
    """Per-dimension summary for *run_id* against its default baselines; empty
    when the run has no reports on disk (a dashboard must still render)."""
    try:
        diff = diff_runs(reports_root, project, run_id, None)
    except (FileNotFoundError, OSError, ValueError):
        return {}
    return {dim: _reduce(entry) for dim, entry in diff.get("dimensions", {}).items()}
