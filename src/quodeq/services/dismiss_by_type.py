"""``dismiss_by_type`` closes every active finding of one requirement code in a scope."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quodeq.core.events.models import FindingDismissed, FindingDismissedEvent
from quodeq.core.finding_identity import snippet_fingerprint
from quodeq.services._violation_filters import unsuppressed
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.wiring import ActionLogWriter, iter_readable_eval_reports

_KEY_VIOLATIONS = "violations"


@dataclass(frozen=True, slots=True)
class DismissScope:
    """Which findings to dismiss: one requirement code in one dimension,
    narrowed to a principle and/or a file when given."""

    req: str
    dimension: str
    principle: str | None = None
    file: str | None = None
    reason: str | None = None


def _in_scope(violation: dict, scope: DismissScope) -> bool:
    if not scope.req or violation.get("req") != scope.req:
        return False
    if scope.principle is not None and violation.get("principle") != scope.principle:
        return False
    return scope.file is None or violation.get("file") == scope.file


def _report_violations(run_dir: Path, dimension: str) -> list[dict]:
    """The dimension's report violations: the report is what the UI counts,
    and every run has one, event log or not."""
    wanted = dimension.lower()
    for dim, report in iter_readable_eval_reports(run_dir):
        if isinstance(report, dict) and str(dim).lower() == wanted:
            return list(report.get(_KEY_VIOLATIONS) or [])
    return []


def select_findings(run_dir: Path, scope: DismissScope) -> list[dict]:
    """Active (not dismissed, not deleted) report violations of *run_dir*
    inside *scope*."""
    project_dir = run_dir.parent
    active = unsuppressed(
        _report_violations(run_dir, scope.dimension),
        dismissed_keys(project_dir), deleted_keys(project_dir), scope.dimension, None,
    )
    return [v for v in active if _in_scope(v, scope)]


def _event(violation: dict, scope: DismissScope) -> FindingDismissedEvent:
    payload = FindingDismissed(
        req=scope.req, file=violation["file"], line=int(violation.get("line") or 0), reason=scope.reason,
        fingerprint=snippet_fingerprint(scope.req, violation.get("snippet")),
    )
    return FindingDismissedEvent(payload=payload)


def dismiss_by_type(project_dir: Path, run_dir: Path, scope: DismissScope) -> int:
    """Emit one dismissal per finding in *scope* that is not dismissed yet,
    in one batch. Returns how many were emitted."""
    events = [_event(v, scope) for v in select_findings(run_dir, scope)]
    ActionLogWriter(project_dir).emit_many(events)
    return len(events)
