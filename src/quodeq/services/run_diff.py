"""Diff one run against another, per dimension, from their dimension reports."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.core.run.state import TERMINAL_STATES, parse_run_state
from quodeq.core.run_diff import RunDiff, diff_findings
from quodeq.core.utils.io import resolve_child_dir
from quodeq.services.wiring import iter_readable_eval_reports, project_run_dates, read_status

LIST_CAP = 200  # entries per list in the payload; the counts are always complete
_KEY_VIOLATIONS = "violations"
_KEY_COMPLIANCE = "compliance"
_KEY_STATE = "state"


def _run_dir(project_dir: Path, run_id: str) -> Path:
    found = resolve_child_dir(project_dir, run_id)
    if found is None:
        raise FileNotFoundError(run_id)
    return Path(found)


def _reports(run_dir: Path) -> dict[str, dict]:
    return {dim: rep for dim, rep in iter_readable_eval_reports(run_dir) if isinstance(rep, dict)}


def _files_seen(report: dict) -> set[str]:
    return {str(f.get("file") or "") for key in (_KEY_VIOLATIONS, _KEY_COMPLIANCE)
            for f in report.get(key) or []}


def _previous_terminal_run(reports_root: Path, project: str, project_dir: Path, run_id: str) -> str | None:
    """The newest run older than *run_id* whose status is terminal."""
    dated = project_run_dates(reports_root, project)  # {run_id: (date_iso, date_label)}
    ordered = sorted(dated, key=lambda rid: dated[rid][0], reverse=True)
    if run_id not in ordered:
        return None
    for candidate in ordered[ordered.index(run_id) + 1:]:
        candidate_dir = resolve_child_dir(project_dir, candidate)
        status = (read_status(Path(candidate_dir)) if candidate_dir else None) or {}
        state = status.get(_KEY_STATE)
        if state and parse_run_state(state) in TERMINAL_STATES:
            return candidate
    return None


def _payload(diff: RunDiff) -> dict[str, Any]:
    return {
        "counts": {
            "carried": len(diff.carried), "same": len(diff.same), "moved": len(diff.moved),
            "new": len(diff.new), "resolved": len(diff.resolved),
            "notReevaluated": len(diff.not_reevaluated),
        },
        "majorsDelta": diff.majors_delta,
        "types": {
            "closed": diff.types_closed, "opened": diff.types_opened,
            "perReq": {req: list(counts) for req, counts in diff.per_req.items()},
        },
        "new": diff.new[:LIST_CAP], "resolved": diff.resolved[:LIST_CAP], "moved": diff.moved[:LIST_CAP],
    }


def diff_runs(reports_root: Path, project: str, run_id: str, against: str | None) -> dict[str, Any]:
    """Per-dimension diff of *run_id* against *against* (default: the previous terminal run)."""
    project_dir = _run_dir(reports_root, project)
    against = against or _previous_terminal_run(reports_root, project, project_dir, run_id)
    current = _reports(_run_dir(project_dir, run_id))
    previous = _reports(_run_dir(project_dir, against)) if against else {}
    dimensions = {
        dim: _payload(diff_findings(
            previous.get(dim, {}).get(_KEY_VIOLATIONS) or [],
            report.get(_KEY_VIOLATIONS) or [],
            current_files=_files_seen(report),
        ))
        for dim, report in current.items()
    }
    return {"runId": run_id, "againstRunId": against, "dimensions": dimensions}
