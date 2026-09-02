"""Request plumbing for assistant routes: repo/context construction, busy check.

Split (Task 10) into three modules plus this thin facade:
  - _assistant_hygiene.py: ``run_assistant_hygiene``, ``_session_ttl_days``,
    ``SharedSourceUnavailable``.
  - _assistant_location.py: ``resolve_run_location``,
    ``resolve_shared_run_location``, ``repo_attach_info``,
    ``resolve_repo_root``.
  - _assistant_events.py: ``event_frames``, ``_POLL_SECONDS``, ``_IDLE_LIMIT``.

The moved names stay imported here (re-exported) so callers across the
codebase and tests can keep patching/importing "quodeq.api._assistant_helpers.
<name>" — the split modules look several of them up on this module at call
time rather than binding their own copies, so a patch here still lands.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from flask import Flask, current_app

from quodeq.assistant import AssistantRepository, AssistantStore
from quodeq.assistant.tools import ToolContext, default_findings_repo_factory
from quodeq.assistant.tools._actions import ActionContext
from quodeq.assistant import LOCAL_PROVIDERS as _LOCAL_PROVIDERS
from quodeq.services.standards_prefs import load_visible_standard_ids
from quodeq.services.shared_repo import (
    read_state,
    shared_evaluations_root,
    shared_score_cache_path,
)
from quodeq.services.shared_settings import read_settings
from quodeq.shared._env import get_evaluations_dir

from quodeq.api._assistant_hygiene import (  # noqa: F401 — re-export/patch target
    SharedSourceUnavailable,
    _session_ttl_days,
    run_assistant_hygiene,
)
from quodeq.api._assistant_location import (  # noqa: F401 — re-export/patch target
    repo_attach_info,
    resolve_repo_root,
    resolve_run_location,
    resolve_shared_run_location,
)
from quodeq.api._assistant_events import (  # noqa: F401 — re-export/patch target
    _IDLE_LIMIT,
    _POLL_SECONDS,
    event_frames,
)


def get_repository(app: Flask) -> AssistantStore:
    if not hasattr(app, "_assistant_repository"):
        app._assistant_repository = AssistantRepository(
            Path(app.config["ASSISTANT_DB_PATH"])
        )
    return app._assistant_repository


def build_action_context(app: Flask) -> ActionContext:
    """Build an ActionContext from app.config, resolved fresh per request.

    ``EVALUATIONS_DIR`` must be read at apply time, not baked in at
    ``create_app`` — tests monkeypatch ``app.config`` before POSTing to
    ``/api/assistant/actions/<id>/apply`` and expect that to take effect
    (see tests/api/test_assistant_routes.py's apply-action tests).
    """
    return ActionContext(
        evaluations_dir=Path(app.config.get("EVALUATIONS_DIR") or get_evaluations_dir()),
        evaluators_dir=Path(app.config["STANDARDS_EVALUATORS_DIR"]),
        compiled_dir=Path(app.config["STANDARDS_COMPILED_DIR"]),
        dimensions_file=Path(app.config["STANDARDS_DIMENSIONS_FILE"]),
    )


def _resolve_shared_source(session: dict) -> tuple[Path, Path | None]:
    """(reports_dir, score_cache_path) for the session's source.

    Local sessions read the regular evaluations dir with no per-clone score
    cache. Shared sessions resolve reports_dir against the shared clone and
    carry the per-clone score-cache path; raises SharedSourceUnavailable when
    no shared repository is configured or its local clone state is unusable
    (the messages route maps this to a 409 rather than a 500). A
    format-version bump or a foreign clone pulled in by a background refresh
    must stop an already-open session's reads too, same as every
    /api/shared/* route enforces at request time.
    """
    if (session.get("source") or "local") != "shared":
        return Path(get_evaluations_dir()), None
    settings = read_settings()
    if not settings.url:
        raise SharedSourceUnavailable("shared repository not configured")
    state = read_state(settings.url)
    if state not in ("ok", "empty"):
        raise SharedSourceUnavailable(f"shared repository unavailable: {state}")
    return shared_evaluations_root(settings.url), shared_score_cache_path(settings.url)


def build_tool_context(
    app: Flask, session: dict, *, repo_root_resolver: Callable[[str], str | None] = resolve_repo_root,
) -> ToolContext:
    """Build a ToolContext from a session row.

    Plan 1 naming note: the session row's ``run_id`` column holds the UI's
    ``runDir`` and ``project_uuid`` holds the UI's ``repoRoot`` — the
    create-session route maps those request fields onto these columns.
    Plan 3 revisits this naming with a schema v2 if needed.
    """
    run_dir = session.get("run_id")
    source = session.get("source") or "local"
    reports_dir, score_cache_path = _resolve_shared_source(session)
    repo_root = (
        Path(session["project_uuid"]) if session.get("project_uuid") else None)
    # Shared sessions never attach a local repo root (the clone has no
    # working copy -- see repo_root's "no_project"/"online_project" handling
    # in assistant_routes.create_session): guard the project_id fallback to
    # local sessions only, so it can't resolve a coincidental local project
    # of the same id into a shared, read-only session's context. The fallback
    # can flip a local session from no-repo-access to repo-access; it fires
    # only when session-creation-time resolution failed, and it recomputes the
    # identical repo_attach_info check rather than a looser one, so it is a
    # self-healing retry rather than a widening of trust.
    if repo_root is None and source != "shared" and session.get("project_id"):
        resolved = repo_root_resolver(session["project_id"])
        repo_root = Path(resolved) if resolved else None
    return ToolContext(
        repository=get_repository(app),
        session_id=session["id"],
        run_dir=Path(run_dir) if run_dir else None,
        repo_root=repo_root,
        evaluators_dir=Path(app.config["STANDARDS_EVALUATORS_DIR"]),
        compiled_dir=Path(app.config["STANDARDS_COMPILED_DIR"]),
        dimensions_file=Path(app.config["STANDARDS_DIMENSIONS_FILE"]),
        project_id=session.get("project_id"),
        reports_dir=reports_dir,
        read_only=(source == "shared"),
        score_cache_path=score_cache_path,
        visible_standard_ids=load_visible_standard_ids(repo_root),
        findings_repo_factory=default_findings_repo_factory,
    )


def local_provider_busy(provider_id: str) -> bool:
    """True when a local single-slot model is likely serving an evaluation."""
    if provider_id not in _LOCAL_PROVIDERS:
        return False
    provider = current_app.config.get("_provider")
    if provider is None:
        return False
    return bool(provider.list_evaluations(limit=20, states={"running"}))
