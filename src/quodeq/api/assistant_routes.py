"""HTTP surface for the embedded assistant (sessions, turns, SSE, actions).

Split into four route modules plus this thin orchestrator:
  - assistant_turn_state.py: ``AssistantTurnState`` and the request-context
    turn-claim shims the workspace routes use.
  - assistant_session_routes.py: create session + skills/actions catalog.
  - assistant_turn_routes.py: post message, stop, SSE events.
  - assistant_action_routes.py: apply / reject a drafted action.

``_api_provider``, ``_known_provider``, and ``_turn_endpoint`` stay here: the
integration tests monkeypatch "quodeq.api.assistant_routes.get_provider_
configs", and these three helpers call it by bare name, so they must keep
resolving it in THIS module's globals. ``_shared_source_error`` stays here
for the same reason (``read_settings``/``read_state`` patch targets), as do
the ``_run_turn``/``_build_tool_context`` shims
("quodeq.api.assistant_routes.run_turn"/"...build_tool_context"). The route
modules receive them as ``SessionGates``/``TurnGates`` instead of importing
this facade.
"""
from __future__ import annotations

from flask import Flask, Response, jsonify

from quodeq.api.assistant_action_routes import register_assistant_action_routes
from quodeq.api.assistant_session_routes import SessionGates, register_assistant_session_routes
from quodeq.api.assistant_turn_routes import TurnGates, register_assistant_turn_routes
from quodeq.api.assistant_turn_state import (  # noqa: F401 — re-export/patch target
    AssistantTurnState,
    _release_turn,
    _try_claim_turn,
    _turn_state,
)
from quodeq.api._assistant_helpers import _LOCAL_PROVIDERS as _FIXED_ENDPOINT_PROVIDERS
from quodeq.api._assistant_helpers import build_tool_context
from quodeq.api.assistant_workspace_routes import register_assistant_workspace_routes
from quodeq.api.helpers import error_response
from quodeq.assistant import get_provider_configs
from quodeq.assistant.orchestrator import TurnRequest, run_turn
from quodeq.assistant.tools import ToolContext
from quodeq.services.shared_repo import REPO_FORMAT_EMPTY, REPO_FORMAT_OK, read_state
from quodeq.services.shared_settings import read_settings


def _api_provider(provider_id: str) -> dict | None:
    # get_provider_configs() returns dict[str, dict] keyed by provider id
    # (see src/quodeq/analysis/provider_cache.py:67 and the top-level keys
    # of data/config/ai_providers.json) — not the {"providers": [...]} list
    # shape the original plan assumed.
    cfg = get_provider_configs().get(provider_id)
    if cfg is None or cfg.get("type") != "api":
        return None
    return cfg


def _known_provider(provider_id: str) -> dict | None:
    """Any catalog entry regardless of type (api or cli); unknown ids are None."""
    return get_provider_configs().get(provider_id)


def _shared_source_error() -> tuple[Response, int] | None:
    """The shared-clone gate for a new session: the 409 body when no shared
    repository is configured or its local clone state is unusable, else None."""
    settings = read_settings()
    if not settings.url:
        body, status = error_response("no shared repository configured", 409, "NO_SHARED_REPO")
        return jsonify(body), status
    state = read_state(settings.url)
    if state not in (REPO_FORMAT_OK, REPO_FORMAT_EMPTY):
        body, status = error_response(f"shared repository unavailable: {state}", 409, "SHARED_REPO_UNAVAILABLE")
        return jsonify(body), status
    return None


def _turn_endpoint(provider: str, body: dict, provider_cfg: dict) -> tuple[str, str | None]:
    """``(api_base, api_key)`` for a turn — the trust boundary for both.

    api_base is ALWAYS the server's catalog value, never the request body: a
    caller-supplied apiBase would redirect the turn (and its tool calls) at an
    arbitrary host (SSRF into internal services / cloud metadata). The UI never
    sends one — provider endpoints live in ai_providers.json. api_key may still
    come from the request for genuinely caller-defined providers
    (custom/openrouter) — it's a credential the caller supplies, not a fetch
    target — falling back to server config; fixed-endpoint local providers need
    none.
    """
    catalog_cfg = _known_provider(provider)
    # CLI providers (claude/codex/gemini) have no HTTP endpoint to pin or
    # override — the orchestrator's run_turn dispatches them internally
    # (spawning the CLI subprocess), so apiBase/apiKey are meaningless here and
    # left unset.
    if catalog_cfg is not None and catalog_cfg.get("type") == "cli":
        return "", None
    if provider in _FIXED_ENDPOINT_PROVIDERS:
        return provider_cfg.get("api_base", ""), None
    return provider_cfg.get("api_base", ""), body.get("apiKey") or provider_cfg.get("api_key")


def _run_turn(request: TurnRequest, **kwargs) -> None:
    """Call ``run_turn`` through this module's globals, so a monkeypatched
    "quodeq.api.assistant_routes.run_turn" still takes effect for a turn that
    was registered before the patch."""
    run_turn(request, **kwargs)


def _build_tool_context(app: Flask, session: dict) -> ToolContext:
    """``build_tool_context`` through this module's globals (see ``_run_turn``)."""
    return build_tool_context(app, session)


def register_assistant_routes(app: Flask) -> None:
    """Bind every assistant route: workspace, sessions, turns, actions."""
    _turn_state(app)  # ensure the registry exists even on bare test apps
    register_assistant_workspace_routes(app)
    register_assistant_session_routes(
        app, SessionGates(known_provider=_known_provider, shared_source_error=_shared_source_error),
    )
    register_assistant_turn_routes(app, TurnGates(
        api_provider=_api_provider,
        turn_endpoint=_turn_endpoint,
        shared_source_error=_shared_source_error,
        run_turn=_run_turn,
        build_tool_context=_build_tool_context,
    ))
    register_assistant_action_routes(app)
