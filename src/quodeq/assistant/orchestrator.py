"""Turn lifecycle: persist → contextualize → run adapter → persist → emit."""
from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass

from quodeq.assistant._context import build_system_prompt, build_turn_message
from quodeq.assistant._turn_grants import (  # noqa: F401 — re-export
    ISOLATED_MCP_STYLES,
    TurnGrants,
    attached_git_repo,
    mcp_server_args,
    provider_type,
    resolve_write_grant,
    write_available,
    write_safe_provider,
)
from quodeq.assistant.adapters.api import ApiTurnConfig, ApiTurnSession, run_api_turn
from quodeq.assistant.adapters.capabilities import supports_native_tools
from quodeq.assistant.adapters.cli import CliTurnConfig, CliTurnSession, run_cli_turn
from quodeq.assistant.cancel import CancelToken, TurnCancelled
from quodeq.assistant.frame_type import FrameType
from quodeq.config.provider import ProviderType
from quodeq.assistant.guard import MAX_TOOL_ITERATIONS, SKILL_MAX_TOOL_ITERATIONS, WRITE_MAX_TOOL_ITERATIONS
from quodeq.assistant.message_role import MessageRole
from quodeq.assistant.skills import cached_skills
from quodeq.assistant.tools import ToolContext, build_registry, register_web_tools
from quodeq.assistant.tools.write_tools import register_write_tools
from quodeq.data.ports.assistant import AssistantStore
from quodeq.llm_bridge import LOCAL_PROVIDERS
from quodeq.services.score_cache import score_cache_path_override
from quodeq.shared.fault_isolation import run_isolated

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TurnRequest:
    """Everything one turn needs from the route: the user text, the UI state to
    contextualize it with, the provider/model to run it on and the web/write
    toggles."""

    session_id: str
    text: str
    ui_state: dict | None
    api_base: str
    api_key: str | None
    provider: str
    model: str
    web_enabled: bool = False
    write_enabled: bool = False


@dataclass(frozen=True, slots=True)
class TurnEngines:
    """Injection points for :func:`run_turn`: the API turn runner, the
    native-tool capability probe, and the CLI turn runner. ``None`` selects
    the production implementation, so tests override only what they fake."""

    turn_fn: Callable | None = None
    capability_fn: Callable | None = None
    cli_turn_fn: Callable | None = None


@dataclass(frozen=True)
class _EngineDeps:
    repository: AssistantStore
    emit: Callable[[dict], None]
    cancel: CancelToken
    turn_fn: Callable
    capability_fn: Callable
    cli_turn_fn: Callable


def _split_skill(text: str):
    if not text.startswith("/"):
        return None, text
    name, _, rest = text[1:].partition(" ")
    return name, rest.strip()


def _run_cli_engine(request: TurnRequest, tool_ctx: ToolContext, messages: list[dict],
                     skill, deps: _EngineDeps) -> str:
    skill_block = (f"[skill:{skill.name}]\n{skill.instructions}"
                   if skill is not None else "")
    prior_session_id = (deps.repository.get_session(request.session_id) or {}).get(
        "cli_session_id")
    return deps.cli_turn_fn(
        messages=messages,
        config=CliTurnConfig(
            provider=request.provider, model=request.model,
            scratch_base=tool_ctx.repository.db_path.parent,
            mcp_server_args=mcp_server_args(request, tool_ctx),
            db_path=tool_ctx.repository.db_path,
            web_enabled=request.web_enabled,
            system_prompt=messages[0]["content"],
            skill_block=skill_block,
            worktree_dir=tool_ctx.worktree_dir,
        ),
        session=CliTurnSession(
            session_id=request.session_id, prior_session_id=prior_session_id,
            repository=deps.repository, emit=deps.emit, cancel=deps.cancel,
        ),
    )


def _run_api_engine(request: TurnRequest, messages: list[dict], skill,
                     grants: TurnGrants, deps: _EngineDeps) -> str:
    config = ApiTurnConfig(
        api_base=request.api_base, api_key=request.api_key,
        model=request.model,
        native_tools=deps.capability_fn(request.provider, request.api_base,
                                        request.model),
        max_tool_iterations=max(
            SKILL_MAX_TOOL_ITERATIONS if skill is not None else MAX_TOOL_ITERATIONS,
            WRITE_MAX_TOOL_ITERATIONS if grants.write_on else 0),
    )
    registry = build_registry(grants.tool_ctx)
    if grants.web_tools_on:
        register_web_tools(registry)
    if grants.write_on:
        register_write_tools(registry, grants.tool_ctx)
    session = ApiTurnSession(registry=registry, emit=deps.emit, cancel=deps.cancel)
    return deps.turn_fn(messages=messages, config=config, session=session)


def _build_deps(request: TurnRequest, repository: AssistantStore, engines: TurnEngines,
                cancel: CancelToken) -> _EngineDeps:
    """Production collaborators for the turn, with *engines* overriding any of the three runners."""
    emit = lambda frame: repository.append_event(request.session_id, frame)  # noqa: E731
    return _EngineDeps(repository=repository, emit=emit, cancel=cancel,
                       turn_fn=engines.turn_fn or run_api_turn,
                       capability_fn=engines.capability_fn or supports_native_tools,
                       cli_turn_fn=engines.cli_turn_fn or run_cli_turn)


def _resolve_skill(raw_text: str) -> tuple[object | None, str, str | None]:
    """``(skill, text, unknown_name)``: the loaded ``/skill`` prefix of *raw_text*, if any.

    ``unknown_name`` is set (and ``skill`` None) when the prefix names no
    loaded skill.
    """
    skill_name, text = _split_skill(raw_text)
    if skill_name is None:
        return None, text, None
    skill = cached_skills().get(skill_name)
    return skill, text, (skill_name if skill is None else None)


def _persist_user_turn(request: TurnRequest, repository: AssistantStore, text: str) -> list[dict]:
    """Record the user's message and return the session history including it."""
    user_content = build_turn_message(text, request.ui_state)
    repository.add_message(request.session_id, MessageRole.USER, user_content)
    return repository.list_messages(request.session_id)


def _compose_messages(skill, grants: TurnGrants, history: list[dict]) -> list[dict]:
    return [{"role": MessageRole.SYSTEM,
             "content": build_system_prompt(skill=skill,
                                            web_enabled=grants.web_tools_on,
                                            write_enabled=grants.write_on)},
            *({"role": m["role"], "content": m["content"]} for m in history)]


def _run_engine(request: TurnRequest, messages: list[dict], skill,
                grants: TurnGrants, deps: _EngineDeps) -> str:
    if provider_type(request.provider) == ProviderType.CLI:
        return _run_cli_engine(request, grants.tool_ctx, messages, skill, deps)
    return _run_api_engine(request, messages, skill, grants, deps)


def _execute_turn(request: TurnRequest, tool_ctx: ToolContext, deps: _EngineDeps) -> None:
    """The happy path of one turn: persist, contextualize, run the engine, persist, emit."""
    skill, text, unknown_skill = _resolve_skill(request.text)
    if unknown_skill is not None:
        deps.emit({"type": FrameType.ERROR, "message": f"unknown skill: /{unknown_skill}"})
        return
    history = _persist_user_turn(request, deps.repository, text)
    # In-process web tools are local-API-only: claude gets NATIVE web
    # tools via argv, and cloud APIs (openrouter/custom) stay excluded.
    web_tools_on = request.web_enabled and request.provider in LOCAL_PROVIDERS
    grants = resolve_write_grant(request, deps.repository, tool_ctx, web_tools_on)
    final = _run_engine(request, _compose_messages(skill, grants, history), skill, grants, deps)
    deps.repository.add_message(request.session_id, MessageRole.ASSISTANT, final)
    deps.emit({"type": FrameType.DONE})


def _run_turn_body(request: TurnRequest, repository: AssistantStore, tool_ctx: ToolContext,
                   engines: TurnEngines | None, cancel: CancelToken | None) -> None:
    """One turn: persist, contextualize, run the engine, persist, emit. A user
    stop (``TurnCancelled``) is handled here, not by ``run_turn``'s
    ``run_isolated`` boundary, so it becomes a ``stopped`` event, not a
    logged failure."""
    deps = _build_deps(request, repository, engines or TurnEngines(), cancel or CancelToken())
    emit = deps.emit
    cache_ctx = score_cache_path_override(tool_ctx.score_cache_path) if tool_ctx.score_cache_path is not None else nullcontext()
    try:
        with cache_ctx:
            _execute_turn(request, tool_ctx, deps)
    except TurnCancelled as exc:
        # User-initiated stop, not a failure. Persist any partial answer so
        # the next turn's replayed history matches what the user saw.
        if exc.partial:
            repository.add_message(request.session_id, MessageRole.ASSISTANT, exc.partial)
        emit({"type": FrameType.STOPPED})


def run_turn(request: TurnRequest, *, repository: AssistantStore,
             tool_ctx: ToolContext, engines: TurnEngines | None = None,
             cancel: CancelToken | None = None) -> None:
    """Run one turn end to end. ``run_isolated`` is the turn thread's
    fault-isolation boundary (the only caller is
    ``assistant_turn_routes._worker``): anything but a user stop (handled
    inside ``_run_turn_body``) is logged with its traceback and becomes a
    generic ``error`` event."""
    run_isolated(
        lambda: _run_turn_body(request, repository, tool_ctx, engines, cancel),
        label=f"assistant turn for session {request.session_id}", log=_logger,
        on_error=lambda _exc: repository.append_event(request.session_id, {
            "type": FrameType.ERROR,
            "message": "The assistant hit an unexpected error. Check the server logs for details."}),
    )
