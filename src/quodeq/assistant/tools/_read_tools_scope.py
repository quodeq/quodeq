"""Session scope for the read tools: run/project selection, the accumulated
(per-dimension-latest) view, and the finding-identity index used to validate
dismiss/verify drafts.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.assistant.tools import _read_tools as _facade
from quodeq.assistant.tools import _read_tools_violations as _violations_facade
from quodeq.assistant.tools._context import ToolContext
from quodeq.assistant.tools._registry import ToolError
from quodeq.data.ports.findings import FindingsRepository
from quodeq.services import _fs_reports
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.scoring import rescore_accumulated, scored_run_dimensions
from quodeq.shared.serialization import to_camel_dict

_logger = logging.getLogger(__name__)


def _findings_repo(ctx: ToolContext, run_dir: Path) -> FindingsRepository:
    factory = ctx.findings_repo_factory or _facade.default_findings_repo_factory
    return factory(run_dir)


def _require_run(ctx: ToolContext):
    if ctx.run_dir is None or not ctx.run_dir.exists():
        raise ToolError(
            "no run selected for this session. Call get_context to confirm "
            "scope. For project overview sessions, use get_violations or "
            "get_report instead of search_findings.")
    return ctx.run_dir


def _has_run(ctx: ToolContext) -> bool:
    """A specific run was selected (vs. the accumulated overview scope)."""
    return ctx.run_dir is not None and ctx.run_dir.exists()


def _accumulated_dims(ctx: ToolContext, *, rescored: bool = True) -> list[dict] | None:
    """Per-dimension-latest composition (the dashboard/overview data).

    Each entry is one dimension sourced from ITS OWN latest run — so the set
    can span several runs, exactly like the dashboard. Carries overallScore/
    Grade, principles, violations and the source run (``fromRunId``). Returns
    None when the session has no project scope.

    By default the project-wide dismiss/delete rescore is applied so the
    scores the model quotes match the Overview (``get_project_scores``) — the
    raw ``compute_accumulated`` payload filters dismissed violations from the
    lists but leaves the baked pre-triage scores untouched.
    ``rescored=False`` returns that raw payload; it exists for
    ``finding_keys_in_scope``, which must keep seeing every finding a
    dismiss/verify key could legitimately reference.
    """
    if ctx.reports_dir is None or ctx.project_id is None:
        return None
    payload = _fs_reports.get_accumulated(str(ctx.reports_dir), ctx.project_id, None)
    if payload is None:
        return None
    if rescored:
        payload = rescore_accumulated(payload, ctx.reports_dir, ctx.project_id)
    return payload.get("dimensions", []) or []


def _scored_run_dims(ctx: ToolContext) -> list[dict] | None:
    """The selected run's dimensions with the project-wide dismiss/delete
    rescore applied, as camelCase dicts.

    Routes through ``scored_run_dimensions`` — the same seam the explorer,
    dashboard and dimension detail read through — so the assistant quotes the
    same dismiss-adjusted score as every UI surface. Returns None when the
    project has no active dismissals/deletions (callers keep the raw eval-JSON
    read: byte-identical output, no parse round-trip) or when the run's
    location can't be resolved against the reports tree (fail-open: raw data
    beats erroring the chat turn).
    """
    project_dir = ctx.run_dir.parent
    try:
        if not dismissed_keys(project_dir) and not deleted_keys(project_dir):
            return None
        dims = scored_run_dimensions(project_dir.parent, project_dir.name, ctx.run_dir.name)
    except Exception:  # noqa: BLE001 - unresolvable layout: serve raw, not a ToolError
        return None
    return [to_camel_dict(d) for d in dims]


def _no_scope_error() -> ToolError:
    return ToolError(
        "no project or run scope for this session. Call get_context to confirm "
        "scope, then ask the user to open a project overview or select a run.")


def finding_keys_in_scope(ctx: ToolContext) -> set[tuple]:
    """Every ``(req, file, line)`` identity the model can see in this scope.

    Used to validate a dismiss/verify draft against a real finding before it is
    recorded, so the model cannot persist an action whose key matches nothing.
    Unions EVERY source a read tool can surface, so the check never falsely
    rejects a finding the model legitimately saw:

    - run scope: the UNCAPPED eval-JSON violations (get_report/get_violations)
      AND the SQL findings table (search_findings) -- the two can drift, and a
      finding present in only one must still be dismissable.
    - overview scope: the accumulated per-dimension-latest violations.

    Best-effort: each source is guarded independently so one unreadable source
    (e.g. a missing eval dir or a corrupt evaluation.db) still leaves the others
    usable, and a wholly unreadable scope surfaces as "no matching finding"
    rather than a stack trace.
    """
    keys: set[tuple] = set()

    def _add(v: dict) -> None:
        keys.add((_violations_facade._requirement_of(v), str(v.get("file") or ""),
                  _violations_facade._coerce_line(v.get("line"))))

    if _has_run(ctx):
        eval_dir = ctx.run_dir / "evaluation"
        if eval_dir.is_dir():
            # Parse each dimension file INDEPENDENTLY: one corrupt/truncated file
            # (a known failure mode of deadline-cut runs) must drop only its own
            # findings, not discard every healthy dimension's keys.
            for p in sorted(eval_dir.glob("*.json")):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                for v in (data.get("violations") or []):
                    _add(v)
        # SQL findings (the search_findings source). Read only an EXISTING db so
        # a read-only draft never creates evaluation.db or kicks a projection on
        # a run that has none -- when there is no db there are no SQL findings to
        # miss anyway.
        if (ctx.run_dir / "evaluation.db").is_file():
            try:
                for f in _findings_repo(ctx, ctx.run_dir).list_all():
                    keys.add((str(f.req or ""), str(f.file or ""),
                              _violations_facade._coerce_line(f.line)))
            except Exception:  # noqa: BLE001 - a corrupt db must not block the read
                _logger.warning(
                    "evaluation.db unreadable in %s; finding keys may be incomplete",
                    ctx.run_dir, exc_info=True)
    else:
        try:
            # rescored=False: the identity check must keep seeing every finding
            # a dismiss/verify key could reference, including already-dismissed
            # ones (idempotent re-dismiss / verify must still match).
            for d in (_accumulated_dims(ctx, rescored=False) or []):
                for v in (d.get("violations") or []):
                    _add(v)
        except (ToolError, OSError, ValueError):
            pass
    return keys
