"""Request plumbing for assistant routes: repo/context construction, busy check."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from flask import Flask, current_app

from quodeq.assistant import AssistantRepository
from quodeq.assistant.tools import ToolContext
from quodeq.assistant import LOCAL_PROVIDERS as _LOCAL_PROVIDERS
from quodeq.services._fs_projects import get_project_info
from quodeq.shared._env import get_evaluations_dir

_logger = logging.getLogger(__name__)

# ~/.quodeq/assistant.db is never pruned otherwise; a session older than this
# is effectively dead (its worktree, if any, was reaped long before). 0
# disables. Whole-session delete cascades to its messages/events/actions.
_DEFAULT_SESSION_TTL_DAYS = 90


def _session_ttl_days() -> int:
    raw = os.environ.get("QUODEQ_ASSISTANT_SESSION_TTL_DAYS")
    if raw is None:
        return _DEFAULT_SESSION_TTL_DAYS
    try:
        return max(0, int(raw))
    except ValueError:
        return _DEFAULT_SESSION_TTL_DAYS


def run_assistant_hygiene(app: Flask) -> None:
    """One-shot-per-process cleanup: reap leaked worktrees, prune old sessions.

    Runs on the first assistant request. Worktrees are GC'd BEFORE the session
    prune so a pruned session's on-disk worktree/branch is already gone.
    Never raises — hygiene must not break the request that triggered it.
    """
    if getattr(app, "_assistant_hygiene_done", False):
        return
    app._assistant_hygiene_done = True
    from quodeq.assistant.worktree import gc_worktrees  # noqa: PLC0415
    repo = get_repository(app)
    try:
        gc_worktrees(repo)
        removed = repo.prune_sessions_older_than(_session_ttl_days())
        if removed:
            _logger.info("Pruned %d old assistant session(s)", removed)
    except Exception:  # noqa: BLE001 — hygiene is best-effort
        _logger.warning("assistant hygiene failed", exc_info=True)

_POLL_SECONDS = 0.25
_IDLE_LIMIT = 2400  # 2400 * 0.25s = 600s idle backstop. The stream now stays
# open across turns (done/error no longer end event_frames), so this bounds a
# session that sits idle with NO new frames for the whole window — a turn that
# dies without emitting a terminal frame (e.g. a crashed daemon thread), or a
# session left open with no further turns. On the backstop the generator
# closes and the client reconnects on its next turn. Sized generously above
# the slowest legitimate gap (a cold-loading local model or a CLI provider's
# ~500s read timeout) so it never truncates a live turn.


def resolve_run_location(project_id: str, run_id: str) -> tuple[str | None, str | None]:
    """Resolve ``(run_dir, repo_root)`` from a ``{projectId, runId}`` pair.

    Reuses the same layout the run index and project routes already rely on
    (see ``services/run_index.py``'s ``_walk_run_dirs`` and
    ``services/_fs_projects.get_project_info``): a run lives at
    ``<evaluations_root>/<project_id>/<run_id>`` where ``project_id`` is the
    directory name under ``get_evaluations_dir()`` (Plan-1's "project_uuid"),
    and the repo root is ``repository_info.json``'s ``path`` field, read via
    the existing ``get_project_info`` helper. Returns ``(None, None)`` when
    the run directory does not exist on disk.

    This is only called when the UI selects a SPECIFIC run. On the overview
    the UI sends no runId and the session stays run-unscoped; the assistant's
    detail tools then read the accumulated (per-dimension-latest) composition
    from ``project_id`` + ``reports_dir`` instead — matching the dashboard,
    which picks each dimension's latest run independently rather than binding
    one whole run.
    """
    evaluations_root = Path(get_evaluations_dir())
    # Jail the run dir to the evaluations root: a crafted project_id/run_id
    # (e.g. "../..") must not resolve to a directory outside it. Mirrors the
    # guard in services/_fs_projects.get_project_info (is_relative_to check)
    # and routes_common.reports_dir. Store the RESOLVED path so the session
    # column can never carry ".." segments.
    run_dir = (evaluations_root / project_id / run_id).resolve()
    try:
        run_dir.relative_to(evaluations_root.resolve())
    except ValueError:
        return None, None
    if not run_dir.is_dir():
        return None, None
    return str(run_dir), resolve_repo_root(project_id)


def repo_attach_info(project_id: str | None) -> tuple[str | None, str]:
    """(repo_root, reason) for the UI's attachment chip and write gate.

    Reasons: ok, no_project, unknown_project, no_recorded_path,
    online_project, path_missing."""
    if not project_id:
        return None, "no_project"
    info = get_project_info(get_evaluations_dir(), project_id)
    if info is None:
        return None, "unknown_project"
    path = info.get("path")
    if not path or not isinstance(path, str):
        return None, "no_recorded_path"
    if str(info.get("location", "")).lower() == "online" or "://" in path:
        return None, "online_project"
    if not Path(path).is_dir():
        return None, "path_missing"
    return path, "ok"


def resolve_repo_root(project_id: str) -> str | None:
    """Resolve the project's local working copy from ``project_id`` alone.

    The repo root is a PROJECT-level fact (``repository_info.json``'s
    ``path``), independent of any run: overview/accumulated sessions carry no
    ``runId`` yet still need repo access for the code-reading tools. Returns
    the path only when it is an existing local directory, so online projects
    (whose ``path`` is a URL) and moved/deleted working copies stay detached
    instead of carrying a bogus root. ``get_project_info`` jails the lookup
    to the evaluations root; the stored ``path`` itself is server-side data
    written at analysis time, never client input.
    """
    return repo_attach_info(project_id)[0]


def get_repository(app: Flask) -> AssistantRepository:
    if not hasattr(app, "_assistant_repository"):
        app._assistant_repository = AssistantRepository(
            Path(app.config["ASSISTANT_DB_PATH"])
        )
    return app._assistant_repository


def build_tool_context(app: Flask, session: dict) -> ToolContext:
    """Build a ToolContext from a session row.

    Plan 1 naming note: the session row's ``run_id`` column holds the UI's
    ``runDir`` and ``project_uuid`` holds the UI's ``repoRoot`` — the
    create-session route maps those request fields onto these columns.
    Plan 3 revisits this naming with a schema v2 if needed.
    """
    run_dir = session.get("run_id")
    return ToolContext(
        repository=get_repository(app),
        session_id=session["id"],
        run_dir=Path(run_dir) if run_dir else None,
        repo_root=Path(session["project_uuid"]) if session.get("project_uuid") else None,
        evaluators_dir=Path(app.config["STANDARDS_EVALUATORS_DIR"]),
        compiled_dir=Path(app.config["STANDARDS_COMPILED_DIR"]),
        dimensions_file=Path(app.config["STANDARDS_DIMENSIONS_FILE"]),
        project_id=session.get("project_id"),
        reports_dir=Path(get_evaluations_dir()),
    )


def local_provider_busy(provider_id: str) -> bool:
    """True when a local single-slot model is likely serving an evaluation."""
    if provider_id not in _LOCAL_PROVIDERS:
        return False
    action_provider = current_app.config.get("_provider")
    jobs = getattr(action_provider, "_jobs", None)
    if jobs is None:
        return False
    return any(j.status == "running" for j in jobs.list_jobs(limit=20))


def event_frames(repository: AssistantRepository, session_id: str, after_seq: int):
    """Generator of (seq, frame) tuples or ``None`` heartbeats.

    Replays stored events after ``after_seq``, then polls indefinitely,
    yielding new events (and ``None`` heartbeat sentinels while idle) so a
    SINGLE SSE connection serves EVERY turn in the session, not just the
    first. ``done``/``error`` frames are still yielded — the client uses them
    as turn markers to clear its spinner and start a fresh answer bubble — but
    they no longer end the generator, so a second (or third) turn's frames,
    appended after the first turn's ``done``, still reach the browser.

    Each idle tick with no new rows yields ``None`` (a heartbeat sentinel the
    caller turns into an SSE comment / data frame) instead of sleeping
    silently, so slow-starting local models and long gaps between frames — or
    between turns — don't trip proxy/connection idle timeouts. The idle
    counter resets on ANY new event (including across turns), so only a
    genuinely idle session (no new frames for the whole ``_IDLE_LIMIT``
    window) hits the backstop and closes; the client then reconnects on its
    next turn. Termination is therefore either that idle backstop or the
    client disconnecting (the generator is GC'd → ``GeneratorExit``). The
    traversal stays ordered by seq with ``last`` advancing so no frame is
    missed or duplicated.
    """
    last, idle = after_seq, 0
    while idle < _IDLE_LIMIT:
        rows = repository.events_after(session_id, last)
        if not rows:
            idle += 1
            yield None
            time.sleep(_POLL_SECONDS)
            continue
        idle = 0
        for seq, frame in rows:
            last = seq
            yield seq, frame
