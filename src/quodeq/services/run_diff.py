"""Diff one run against another, per dimension, from their dimension reports."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.core.run.state import TERMINAL_STATES, RunState, parse_run_state
from quodeq.core.run_diff import RunDiff, diff_findings
from quodeq.core.utils.io import resolve_child_dir
from quodeq.services.wiring import (
    iter_readable_eval_reports,
    project_run_dates,
    read_eval_report,
    read_status,
)

LIST_CAP = 200  # entries per list in the payload; the counts are always complete
_KEY_VIOLATIONS = "violations"
_KEY_COMPLIANCE = "compliance"
_KEY_STATE = "state"
_KEY_COMMIT_SHA = "commit_sha"
_EVAL_DIR = "evaluation"
_JSON = ".json"


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


def _state_of(run_dir: Path) -> RunState | None:
    """The run's state, or None when status.json is missing, unreadable or unknown."""
    try:
        raw = (read_status(run_dir) or {}).get(_KEY_STATE)
        return parse_run_state(raw) if raw else None
    except (OSError, ValueError, RuntimeError):
        return None


def _commit_sha(run_dir: Path) -> str | None:
    try:
        return (read_status(run_dir) or {}).get(_KEY_COMMIT_SHA)
    except (OSError, RuntimeError):
        return None


def _older_runs(reports_root: Path, project: str, run_id: str) -> list[str]:
    """Runs older than *run_id* by ``started_at``, newest first."""
    dated = project_run_dates(reports_root, project)  # {run_id: (date_iso, date_label)}
    ordered = sorted(dated, key=lambda rid: dated[rid][0], reverse=True)
    return ordered[ordered.index(run_id) + 1:] if run_id in ordered else []


def _baseline_for(project_dir: Path, older: list[str], dimension: str) -> str | None:
    """The newest older run that evaluated *dimension*: a finished one first,
    then any other terminal one (a cancelled run may still hold full reports)."""
    candidates: list[tuple[str, RunState]] = []
    for rid in older:
        run_dir = resolve_child_dir(project_dir, rid)
        if run_dir is None or not (Path(run_dir) / _EVAL_DIR / f"{dimension}{_JSON}").is_file():
            continue
        state = _state_of(Path(run_dir))
        if state in TERMINAL_STATES:
            candidates.append((rid, state))
    for wanted in (RunState.DONE, None):
        for rid, state in candidates:
            if wanted is None or state == wanted:
                return rid
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
    """Per-dimension diff of *run_id*. With *against* every dimension uses that
    run; without it each dimension picks its own baseline (see ``_baseline_for``)
    and reports it as ``againstRunId``."""
    project_dir = _run_dir(reports_root, project)
    current_dir = _run_dir(project_dir, run_id)
    if against:
        _run_dir(project_dir, against)
    older = [] if against else _older_runs(reports_root, project, run_id)
    dimensions: dict[str, Any] = {}
    for dim, report in _reports(current_dir).items():
        base = against or _baseline_for(project_dir, older, dim)
        previous = (read_eval_report(_run_dir(project_dir, base) / _EVAL_DIR, dim) or {}) if base else {}
        entry = _payload(diff_findings(
            previous.get(_KEY_VIOLATIONS) or [],
            report.get(_KEY_VIOLATIONS) or [],
            current_files=_files_seen(report),
        ))
        entry["againstRunId"] = base
        entry["againstCommitSha"] = _commit_sha(_run_dir(project_dir, base)) if base else None
        dimensions[dim] = entry
    return {
        "runId": run_id, "commitSha": _commit_sha(current_dir),
        "againstRunId": against, "dimensions": dimensions,
    }
