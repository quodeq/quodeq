"""Request plumbing for assistant routes: repo/context construction, busy check."""
from __future__ import annotations

import time
from pathlib import Path

from flask import Flask, current_app

from quodeq.assistant import AssistantRepository
from quodeq.assistant.tools import ToolContext
from quodeq.services._fs_projects import get_project_info
from quodeq.shared._env import get_evaluations_dir

_LOCAL_PROVIDERS = frozenset({"ollama", "llamacpp", "omlx"})
_POLL_SECONDS = 0.25
_IDLE_LIMIT = 2400  # 2400 * 0.25s = 600s safety cap for a turn that dies
# without ever emitting a terminal done/error frame (e.g. a crashed daemon
# thread). run_turn always writes done/error on completion, so event_frames
# already terminates correctly then; this is just the outer guard for the
# abnormal case, sized generously above the slowest legitimate turn (a
# cold-loading local model or a CLI provider's ~500s read timeout).


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
    info = get_project_info(str(evaluations_root), project_id)
    repo_root = info.get("path") if info else None
    return str(run_dir), repo_root


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

    Replays stored events after ``after_seq``, then polls until a done/error
    frame arrives or the idle limit is hit. Each idle tick with no new rows
    yields ``None`` (a heartbeat sentinel the caller turns into an SSE
    comment) instead of sleeping silently, so slow-starting local models and
    long gaps between frames don't trip proxy/connection idle timeouts.
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
            if frame.get("type") in ("done", "error"):
                return
