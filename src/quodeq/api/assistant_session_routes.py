"""Session lifecycle routes for the embedded assistant: create + catalog.

Split out of assistant_routes.py (Task 10). ``_known_provider`` and
``_shared_source_error`` are looked up on the ``assistant_routes`` facade at
call time (rather than imported directly here) so that tests patching
"quodeq.api.assistant_routes.get_provider_configs"/"read_settings"/
"read_state" keep working after the split.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from flask import Flask, jsonify, request

from quodeq.api import _assistant_helpers
from quodeq.assistant.orchestrator import write_safe_provider
from quodeq.assistant.skills import RESERVED_COMMANDS, load_skills
from quodeq.assistant.tools._actions import ACTION_DESCRIPTIONS, ACTION_TYPES


def _resolve_session_scope(source: str, body: dict) -> tuple[str | None, str | None, str]:
    """``(run_dir, repo_root, repo_reason)`` for a new session.

    Plan 1 mapping: runDir → run_id column, repoRoot → project_uuid column.
    Client-supplied runDir/repoRoot are NOT honored: they'd flow to the MCP
    subprocess's --run-dir/--repo-root with no path jail, giving a remote
    API-key caller arbitrary server-side file access. The real UI never sends
    these — it sends {projectId, runId} and the server resolves
    run_dir/repo_root itself via the jailed resolver.

    Three shapes:
    - shared: never attaches a repo (the clone has no working copy); data reads
      resolve against the clone's evaluations root in build_tool_context.
    - local + specific runId: binds that one run.
    - local overview (projectId, no runId): stays run-unscoped, so the detail
      tools read the accumulated (per-dimension-latest) composition from
      project_id + reports_dir.
    """
    project_id = body.get("projectId")
    if source == "shared":
        run_dir = None
        if project_id and body.get("runId"):
            run_dir = _assistant_helpers.resolve_shared_run_location(
                str(project_id), str(body["runId"]))
        return run_dir, None, "online_project"
    if not project_id:
        return None, None, "no_project"
    repo_root, repo_reason = _assistant_helpers.repo_attach_info(str(project_id))
    run_dir = None
    if body.get("runId"):
        run_dir, _ = _assistant_helpers.resolve_run_location(
            str(project_id), str(body["runId"]),
        )
    return run_dir, repo_root, repo_reason


def register_assistant_session_routes(app: Flask) -> None:
    @app.post("/api/assistant/sessions")
    def create_assistant_session():
        from quodeq.api import assistant_routes as _assistant_routes  # noqa: PLC0415 — deferred: see module docstring

        # First assistant request of the process: reap leaked worktrees +
        # prune stale sessions before minting a new one (one-shot, best-effort).
        _assistant_helpers.run_assistant_hygiene(app)
        body = request.get_json(silent=True) or {}
        provider_cfg = _assistant_routes._known_provider(str(body.get("provider", "")))
        if provider_cfg is None:
            return jsonify({"error": "unknown or unsupported provider"}), 400
        source = str(body.get("source") or "local")
        if source not in ("local", "shared"):
            return jsonify({"error": "invalid source"}), 400
        if source == "shared":
            shared_error = _assistant_routes._shared_source_error()
            if shared_error is not None:
                return shared_error
        session_id = uuid.uuid4().hex
        run_dir, repo_root, repo_reason = _resolve_session_scope(source, body)
        project_id = body.get("projectId")
        _assistant_helpers.get_repository(app).create_session(
            session_id=session_id, provider=body["provider"],
            model=body.get("model"), project_uuid=repo_root,
            run_id=run_dir,
            project_id=str(project_id) if project_id else None,
            source=source,
        )
        write_available = (source == "local"
                           and bool(repo_root)
                           and (Path(repo_root) / ".git").exists()
                           and write_safe_provider(str(body["provider"])))
        return jsonify({"sessionId": session_id,
                        "repoAttached": repo_root is not None,
                        "repoReason": repo_reason,
                        "readOnly": source == "shared",
                        "writeAvailable": write_available}), 201

    @app.get("/api/assistant/skills")
    def get_assistant_catalog():
        # Static catalog for the drawer's welcome panel, autocomplete, and
        # /help /skills /actions meta-commands. Read-only, no session needed.
        return jsonify({
            "commands": [{"name": n, "description": d} for n, d in RESERVED_COMMANDS],
            "skills": [
                {"name": s.name, "description": s.description,
                 "argumentHint": s.argument_hint, "views": list(s.views),
                 "requiresWrite": s.requires_write}
                for s in load_skills().values()
            ],
            "actions": [
                {"type": t, "description": ACTION_DESCRIPTIONS.get(t, "")}
                for t in sorted(ACTION_TYPES)
            ],
        })
