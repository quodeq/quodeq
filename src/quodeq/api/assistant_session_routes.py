"""Session lifecycle routes for the embedded assistant: create + catalog.

Split out of assistant_routes.py. The provider lookup and the
shared-clone gate are injected by the registrar (``SessionGates``): they live
in ``assistant_routes`` so tests patching
"quodeq.api.assistant_routes.get_provider_configs"/"read_settings"/
"read_state" keep working, and this module never imports that facade.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from flask import Flask, Response, jsonify

from quodeq.api import _assistant_helpers
from quodeq.api._constants import CODE_INVALID_PARAM
from quodeq.api.helpers import error_response, optional_json_object_or_error
from quodeq.assistant import SessionScope
from quodeq.assistant.orchestrator import write_safe_provider
from quodeq.assistant.skills import RESERVED_COMMANDS, cached_skills
from quodeq.assistant.tools.actions import ACTION_DESCRIPTIONS, ACTION_TYPES
from quodeq.core.types.project_source import ProjectSource


@dataclass(frozen=True)
class SessionGates:
    """Checks a new session must pass, supplied by the registering facade."""

    known_provider: Callable[[str], dict | None]
    shared_source_error: Callable[[], tuple[Response, int] | None]


def _validate_session_request(
    body: dict, gates: SessionGates,
) -> tuple[Response | tuple[Response, int] | None, str]:
    """Validate provider + source. Returns ``(error, source)``: *error* is the
    route's early-return value (or None to proceed); *source* is the resolved
    source string, valid whether or not *error* is set.
    """
    provider_cfg = gates.known_provider(str(body.get("provider", "")))
    if provider_cfg is None:
        body_, status = error_response(
            "unknown or unsupported provider", 400, "INVALID_PROVIDER")
        return (jsonify(body_), status), ""
    source = str(body.get("source") or ProjectSource.LOCAL)
    if source not in ProjectSource:
        body_, status = error_response("invalid source", 400, "INVALID_SOURCE")
        return (jsonify(body_), status), source
    if source == ProjectSource.SHARED:
        shared_error = gates.shared_source_error()
        if shared_error is not None:
            return shared_error, source
    return None, source


def _compute_write_available(source: str, repo_root: str | None, provider: str) -> bool:
    return (source == ProjectSource.LOCAL
            and bool(repo_root)
            and (Path(repo_root) / ".git").exists()
            and write_safe_provider(provider))


def _resolve_session_scope(source: str, body: dict) -> tuple[str | None, str | None, str]:
    """``(run_dir, repo_root, repo_reason)`` for a new session.

    runDir maps to the run_id column, repoRoot to the project_uuid column.
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
    if source == ProjectSource.SHARED:
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


def register_assistant_session_routes(app: Flask, gates: SessionGates) -> None:
    """Bind the assistant session lifecycle routes.

    *gates* carries the per-source admission checks, so a caller can stand the
    routes up with a provider disabled without touching this module.
    """
    @app.post("/api/assistant/sessions")
    def create_assistant_session():
        # First assistant request of the process: reap leaked worktrees +
        # prune stale sessions before minting a new one (one-shot, best-effort).
        _assistant_helpers.run_assistant_hygiene(app)
        body = optional_json_object_or_error(CODE_INVALID_PARAM)
        if not isinstance(body, dict):
            return jsonify(body[0]), body[1]
        error, source = _validate_session_request(body, gates)
        if error is not None:
            return error
        session_id = uuid.uuid4().hex
        run_dir, repo_root, repo_reason = _resolve_session_scope(source, body)
        project_id = body.get("projectId")
        _assistant_helpers.get_repository(app).create_session(
            session_id=session_id, provider=body["provider"], model=body.get("model"),
            source=source,
            scope=SessionScope(repo_root, run_dir, str(project_id) if project_id else None),
        )
        write_available = _compute_write_available(source, repo_root, str(body["provider"]))
        return jsonify({"sessionId": session_id,
                        "repoAttached": repo_root is not None,
                        "repoReason": repo_reason,
                        "readOnly": source == ProjectSource.SHARED,
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
                for s in cached_skills().values()
            ],
            "actions": [
                {"type": t, "description": ACTION_DESCRIPTIONS.get(t, "")}
                for t in sorted(ACTION_TYPES)
            ],
        })
