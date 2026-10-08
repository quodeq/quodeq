"""Diff one run against another, per dimension, from their dimension reports."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quodeq.core.run.state import TERMINAL_STATES, RunState, parse_run_state
from quodeq.core.run_diff import RunDiff, diff_findings
from quodeq.core.utils.io import resolve_child_dir
from quodeq.services._fs_project_primitives import local_repo_root
from quodeq.services._violation_filters import unsuppressed
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.run_changes import SCOPE_ALL, SCOPE_CHANGED, changed_files
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
_KEY_COMMIT_DIRTY = "commit_dirty"
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


def _commit_state(run_dir: Path) -> tuple[str | None, bool | None]:
    """``(commit_sha, commit_dirty)`` as recorded at run start, or Nones."""
    try:
        status = read_status(run_dir) or {}
    except (OSError, RuntimeError):
        return None, None
    return status.get(_KEY_COMMIT_SHA), status.get(_KEY_COMMIT_DIRTY)


def _comparable(base: tuple[str | None, bool | None], head: tuple[str | None, bool | None]) -> bool:
    """Two commits bound the change set only when neither tree had uncommitted edits."""
    return not base[1] and not head[1]


_OlderRun = tuple[str, Path, RunState | None]  # (run id, run dir, state)


def _older_runs(reports_root: Path, project: str, run_id: str) -> list[str]:
    """Runs older than *run_id* by ``started_at``, newest first."""
    dated = project_run_dates(reports_root, project)  # {run_id: (date_iso, date_label)}
    ordered = sorted(dated, key=lambda rid: dated[rid][0], reverse=True)
    return ordered[ordered.index(run_id) + 1:] if run_id in ordered else []


def _resolve_older(project_dir: Path, older: list[str]) -> list[_OlderRun]:
    """Locate each older run and read its state once; every dimension reuses them."""
    resolved: list[_OlderRun] = []
    for rid in older:
        run_dir = resolve_child_dir(project_dir, rid)
        if run_dir is not None:
            resolved.append((rid, Path(run_dir), _state_of(Path(run_dir))))
    return resolved


def _baseline_for(older: list[_OlderRun], dimension: str) -> str | None:
    """The newest older run that evaluated *dimension*: a finished one first,
    then any other terminal one (a cancelled run may still hold full reports)."""
    candidates = [
        (rid, state) for rid, run_dir, state in older
        if state in TERMINAL_STATES and (run_dir / _EVAL_DIR / f"{dimension}{_JSON}").is_file()
    ]
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
        "criticalDelta": diff.critical_delta,
        "types": {
            "closed": diff.types_closed, "opened": diff.types_opened,
            "perReq": {req: list(counts) for req, counts in diff.per_req.items()},
        },
        "new": diff.new[:LIST_CAP], "resolved": diff.resolved[:LIST_CAP], "moved": diff.moved[:LIST_CAP],
    }


def _in_scope(findings: list[dict], files: set[str] | None) -> list[dict]:
    return findings if files is None else [f for f in findings if str(f.get("file") or "") in files]


def _since_baseline(
    previous: list[dict], current: list[dict], files: set[str] | None, current_files: set[str],
) -> dict[str, Any]:
    """The diff restricted to *files* (the paths changed between the two
    commits); with *files* None the scope is every file and says so. Cold-cache
    re-sampling of untouched files never lands here."""
    scoped = diff_findings(_in_scope(previous, files), _in_scope(current, files),
                           current_files=current_files)
    return {
        "scope": SCOPE_ALL if files is None else SCOPE_CHANGED,
        "changedFiles": None if files is None else len(files),
        "majorsDelta": scoped.majors_delta,
        "criticalDelta": scoped.critical_delta,
        "counts": {"new": len(scoped.new), "resolved": len(scoped.resolved)},
        "types": {"closed": scoped.types_closed, "opened": scoped.types_opened},
        "new": scoped.new[:LIST_CAP], "resolved": scoped.resolved[:LIST_CAP],
    }


def _baseline_scope(
    project_dir: Path, repo_root: Path | None, base: str | None, head: tuple[str | None, bool | None],
) -> tuple[tuple[str | None, bool | None], set[str] | None]:
    """``(base_commit_state, changed_files)`` for one baseline run; the file
    set is None when the two commits do not bound the change set."""
    if not base:
        return (None, None), None
    base_state = _commit_state(_run_dir(project_dir, base))
    files = changed_files(repo_root, base_state[0], head[0]) if _comparable(base_state, head) else None
    return base_state, files


_CommitState = tuple[str | None, bool | None]
_Scope = tuple[_CommitState, set[str] | None]


@dataclass(frozen=True)
class _DiffContext:
    """What every dimension of one diff shares: the run dirs, project-wide
    suppressions and the head commit."""

    project_dir: Path
    current_dir: Path
    older: list[_OlderRun]
    suppressed: tuple[set, set]  # (dismissed keys, deleted keys)
    repo_root: Path | None
    head: _CommitState


def _locate_runs(
    reports_root: Path, project: str, run_id: str, against: str | None,
) -> tuple[Path, Path, list[_OlderRun]]:
    """``(project_dir, current_dir, older_runs)``; a missing run raises FileNotFoundError."""
    project_dir = _run_dir(reports_root, project)
    current_dir = _run_dir(project_dir, run_id)
    if against:
        _run_dir(project_dir, against)
    older = [] if against else _resolve_older(project_dir, _older_runs(reports_root, project, run_id))
    return project_dir, current_dir, older


def _diff_context(reports_root: Path, project: str, run_id: str, against: str | None) -> _DiffContext:
    project_dir, current_dir, older = _locate_runs(reports_root, project, run_id, against)
    # Dismissals and deletions are project-wide; a dismissed finding is neither
    # new on every run nor resolved when it stops being reported.
    suppressed = (dismissed_keys(project_dir), deleted_keys(project_dir))
    return _DiffContext(
        project_dir, current_dir, older, suppressed,
        local_repo_root(reports_root, project), _commit_state(current_dir),
    )


def _active_findings(ctx: _DiffContext, base: str | None, dim: str, report: dict) -> tuple[list, list]:
    """Unsuppressed ``(baseline, current)`` violations of *dim*."""
    previous = (read_eval_report(_run_dir(ctx.project_dir, base) / _EVAL_DIR, dim) or {}) if base else {}
    dkeys, delkeys = ctx.suppressed
    prev_active = unsuppressed(previous.get(_KEY_VIOLATIONS) or [], dkeys, delkeys, dim, None)
    curr_active = unsuppressed(report.get(_KEY_VIOLATIONS) or [], dkeys, delkeys, dim, None)
    return prev_active, curr_active


def _dimension_entry(
    ctx: _DiffContext, dim: str, report: dict, base: str | None, scope: _Scope,
) -> dict[str, Any]:
    """One dimension's payload: the full diff plus the changed-files view."""
    base_state, files = scope
    prev_active, curr_active = _active_findings(ctx, base, dim, report)
    seen = _files_seen(report)
    entry = _payload(diff_findings(prev_active, curr_active, current_files=seen))
    entry["againstRunId"] = base
    entry["againstCommitSha"], entry["againstCommitDirty"] = base_state
    entry["sinceBaseline"] = _since_baseline(prev_active, curr_active, files, seen)
    return entry


def diff_runs(reports_root: Path, project: str, run_id: str, against: str | None) -> dict[str, Any]:
    """Per-dimension diff of *run_id*. With *against* every dimension uses that
    run; without it each dimension picks its own baseline (see ``_baseline_for``)
    and reports it as ``againstRunId``."""
    ctx = _diff_context(reports_root, project, run_id, against)
    # Several dimensions share one baseline run (always, with *against*);
    # its commit state and the git diff against head are resolved once.
    scopes: dict[str | None, _Scope] = {}
    dimensions: dict[str, Any] = {}
    for dim, report in _reports(ctx.current_dir).items():
        base = against or _baseline_for(ctx.older, dim)
        if base not in scopes:
            scopes[base] = _baseline_scope(ctx.project_dir, ctx.repo_root, base, ctx.head)
        dimensions[dim] = _dimension_entry(ctx, dim, report, base, scopes[base])
    return {
        "runId": run_id, "commitSha": ctx.head[0], "commitDirty": ctx.head[1],
        "againstRunId": against, "dimensions": dimensions,
    }
