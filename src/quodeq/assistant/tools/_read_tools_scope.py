"""Session scope for the read tools: run/project selection, the accumulated
(per-dimension-latest) view, and the finding-identity index used to validate
dismiss/verify drafts.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from quodeq.assistant.tools._context import ToolContext
from quodeq.assistant.tools._read_tools_common import default_findings_repo_factory, requirement_of
from quodeq.assistant.tools.registry import ToolError
from quodeq.data.ports.findings import FindingsRepository
from quodeq.data.sqlite.connection import EVALUATION_DB_FILENAME
from quodeq.services import fs_reports
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.scoring import rescore_accumulated, scored_run_dimensions
from quodeq.services.wiring import iter_eval_reports
from quodeq.shared.lru import LRUDict
from quodeq.shared.serialization import coerce_line, to_camel_dict

_logger = logging.getLogger(__name__)


def findings_repo(ctx: ToolContext, run_dir: Path) -> FindingsRepository:
    """The run's findings repository from the context factory, else the SQLite default."""
    factory = ctx.findings_repo_factory or default_findings_repo_factory
    return factory(run_dir)


def require_run(ctx: ToolContext):
    """The selected run dir, or a ToolError telling the model which tool to use instead."""
    if ctx.run_dir is None or not ctx.run_dir.exists():
        raise ToolError(
            "no run selected for this session. Call get_context to confirm "
            "scope. For project overview sessions, use get_violations or "
            "get_report instead of search_findings.")
    return ctx.run_dir


def has_run(ctx: ToolContext) -> bool:
    """A specific run was selected (vs. the accumulated overview scope)."""
    return ctx.run_dir is not None and ctx.run_dir.exists()


def accumulated_dims(ctx: ToolContext, *, rescored: bool = True) -> list[dict] | None:
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
    payload = fs_reports.get_accumulated(str(ctx.reports_dir), ctx.project_id, None)
    if payload is None:
        return None
    if rescored:
        payload = rescore_accumulated(payload, ctx.reports_dir, ctx.project_id)
    return payload.get("dimensions", []) or []


def scored_run_dims(ctx: ToolContext) -> list[dict] | None:
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


def no_scope_error() -> ToolError:
    """The ToolError for a session with neither a run nor a project scope."""
    return ToolError(
        "no project or run scope for this session. Call get_context to confirm "
        "scope, then ask the user to open a project overview or select a run.")


def _eval_json_finding_keys(ctx: ToolContext, add) -> bool:
    """Keys from the run's UNCAPPED eval-JSON violations (the
    get_report/get_violations source). False when a dimension file could
    not be read, so the caller does not memoize a partial set."""
    eval_dir = ctx.run_dir / "evaluation"
    if not eval_dir.is_dir():
        return True
    # skip_corrupt=True: parse each dimension file INDEPENDENTLY, so one
    # corrupt/truncated file (a known failure mode of deadline-cut runs)
    # drops only its own findings, not every healthy dimension's keys. The
    # helper skips silently, so a report count short of the file count is
    # how a skipped file shows up here.
    expected = len(list(eval_dir.glob("*.json")))
    parsed = 0
    for _dimension, data in iter_eval_reports(eval_dir, skip_corrupt=True):
        parsed += 1
        for v in (data.get("violations") or []):
            add(v)
    return parsed == expected


def _sql_finding_keys(ctx: ToolContext, keys: set[tuple]) -> bool:
    """Keys from the SQL findings table (the search_findings source). Read
    only an EXISTING db so a read-only draft never creates evaluation.db or
    kicks a projection on a run that has none -- when there is no db there
    are no SQL findings to miss anyway. False when the db was unreadable."""
    if not (ctx.run_dir / EVALUATION_DB_FILENAME).is_file():
        return True
    try:
        for req, file, line in findings_repo(ctx, ctx.run_dir).list_keys():
            keys.add((str(req or ""), str(file or ""), coerce_line(line)))
    except Exception:  # noqa: BLE001 - a corrupt db must not block the read
        _logger.warning(
            "evaluation.db unreadable in %s; finding keys may be incomplete",
            ctx.run_dir, exc_info=True)
        return False
    return True


def _accumulated_finding_keys(ctx: ToolContext, add) -> None:
    try:
        # rescored=False: the identity check must keep seeing every finding
        # a dismiss/verify key could reference, including already-dismissed
        # ones (idempotent re-dismiss / verify must still match).
        for d in (accumulated_dims(ctx, rescored=False) or []):
            for v in (d.get("violations") or []):
                add(v)
    except (ToolError, OSError, ValueError) as exc:
        _logger.debug("accumulated findings unavailable for identity keys: %s", exc)


def _identity(v: dict) -> tuple:
    return (requirement_of(v), str(v.get("file") or ""), coerce_line(v.get("line")))


# Run-scope identity keys, memoized per (run dir, repo factory) under a stat
# stamp of every file they are read from. The model often drafts several
# dismissals in one turn; each draft used to re-parse every eval JSON and
# re-query evaluation.db. Bounded so a long-lived server cannot grow it.
_RUN_KEYS_MEMO_SIZE = 64
# A file modified this recently may change again inside the filesystem's
# mtime granularity (coarse on Linux) with the same size, so a stamp taken
# over it cannot prove freshness: such reads are served but not memoized.
_SETTLE_NS = 3_000_000_000
_RUN_KEY_SOURCES = ("evaluation.db", "evaluation.db-wal", "events.jsonl")
_run_keys_memo: LRUDict[tuple, tuple[tuple, frozenset[tuple]]] = LRUDict(_RUN_KEYS_MEMO_SIZE)
_run_keys_lock = threading.Lock()


def _source_stamp(run_dir: Path) -> tuple:
    """(name, mtime_ns, size, ino) for every file the run-scope keys come
    from; a missing file stamps as (name, None, None, None). The inode
    catches a file replaced in place (same mtime, same size, new content)
    that an mtime/size stamp alone would miss."""
    eval_dir = run_dir / "evaluation"
    paths = sorted(eval_dir.glob("*.json")) if eval_dir.is_dir() else []
    paths.extend(run_dir / name for name in _RUN_KEY_SOURCES)
    stamp = []
    for path in paths:
        try:
            st = path.stat()
        except OSError:
            stamp.append((path.name, None, None, None))
        else:
            stamp.append((path.name, st.st_mtime_ns, st.st_size, st.st_ino))
    return tuple(stamp)


def _is_settled(stamp: tuple) -> bool:
    newest = max((mtime for _name, mtime, _size, _ino in stamp if mtime is not None), default=0)
    return newest < time.time_ns() - _SETTLE_NS


def _run_finding_keys(ctx: ToolContext) -> frozenset[tuple]:
    """The run scope's identity keys, from the memo when no source changed.

    A partial read (a corrupt dimension file or an unreadable db) is
    returned but never memoized, so the next draft retries the source.
    """
    memo_key = (ctx.run_dir, ctx.findings_repo_factory)
    stamp = _source_stamp(ctx.run_dir)
    with _run_keys_lock:
        cached = _run_keys_memo.get(memo_key)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    keys: set[tuple] = set()
    complete = _eval_json_finding_keys(ctx, lambda v: keys.add(_identity(v)))
    complete = _sql_finding_keys(ctx, keys) and complete
    frozen = frozenset(keys)
    if complete and _is_settled(stamp):
        with _run_keys_lock:
            _run_keys_memo.put(memo_key, (stamp, frozen))
    return frozen


def finding_keys_in_scope(ctx: ToolContext) -> set[tuple]:
    """Every ``(req, file, line)`` identity the model can see in this scope.

    Used to validate a dismiss/verify draft against a real finding before it is
    recorded, so the model cannot persist an action whose key matches nothing.
    Unions EVERY source a read tool can surface, so the check never falsely
    rejects a finding the model legitimately saw:

    - run scope: the UNCAPPED eval-JSON violations (get_report/get_violations)
      AND the SQL findings table (search_findings) -- the two can drift, and a
      finding present in only one must still be dismissable. Memoized per run
      under a stat stamp of those files (see ``_run_finding_keys``).
    - overview scope: the accumulated per-dimension-latest violations.

    Best-effort: each source is guarded independently so one unreadable source
    (e.g. a missing eval dir or a corrupt evaluation.db) still leaves the others
    usable, and a wholly unreadable scope surfaces as "no matching finding"
    rather than a stack trace.
    """
    if has_run(ctx):
        return set(_run_finding_keys(ctx))
    keys: set[tuple] = set()
    _accumulated_finding_keys(ctx, lambda v: keys.add(_identity(v)))
    return keys
