"""Turn lifecycle: persist → contextualize → run adapter → persist → emit."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from quodeq.assistant import get_provider_configs
from quodeq.assistant._context import build_system_prompt, build_turn_message
from quodeq.assistant.adapters._api import ApiTurnConfig, run_api_turn
from quodeq.assistant.adapters._capabilities import supports_native_tools
from quodeq.assistant.adapters._cli import CliTurnConfig, run_cli_turn
from quodeq.assistant.guard import MAX_TOOL_ITERATIONS, SKILL_MAX_TOOL_ITERATIONS
from quodeq.assistant.skills import load_skills
from quodeq.assistant.tools import ToolContext, build_registry, register_web_tools
from quodeq.data.sqlite.assistant_repository import AssistantRepository
from quodeq.llm_bridge import LOCAL_PROVIDERS

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TurnRequest:
    session_id: str
    text: str
    ui_state: dict | None
    api_base: str
    api_key: str | None
    provider: str
    model: str
    web_enabled: bool = False


def _split_skill(text: str):
    if not text.startswith("/"):
        return None, text
    name, _, rest = text[1:].partition(" ")
    return name, rest.strip()


def _provider_type(provider: str) -> str:
    return get_provider_configs().get(provider, {}).get("type", "cli")


def _mcp_server_args(request: TurnRequest, tool_ctx: ToolContext) -> list[str]:
    args = [
        "--db-path", str(tool_ctx.repository.db_path),
        "--session-id", request.session_id,
        "--evaluators-dir", str(tool_ctx.evaluators_dir),
        "--compiled-dir", str(tool_ctx.compiled_dir),
        "--dimensions-file", str(tool_ctx.dimensions_file),
    ]
    if tool_ctx.run_dir is not None:
        args += ["--run-dir", str(tool_ctx.run_dir)]
    if tool_ctx.repo_root is not None:
        args += ["--repo-root", str(tool_ctx.repo_root)]
    if tool_ctx.project_id is not None:
        args += ["--project-id", str(tool_ctx.project_id)]
    if tool_ctx.reports_dir is not None:
        args += ["--reports-dir", str(tool_ctx.reports_dir)]
    return args


def run_turn(request: TurnRequest, *, repository: AssistantRepository,
             tool_ctx: ToolContext, turn_fn=None, capability_fn=None,
             cli_turn_fn=None) -> None:
    turn_fn = turn_fn or run_api_turn
    capability_fn = capability_fn or supports_native_tools
    cli_turn_fn = cli_turn_fn or run_cli_turn
    emit = lambda frame: repository.append_event(request.session_id, frame)  # noqa: E731
    try:
        skill_name, text = _split_skill(request.text)
        skill = None
        if skill_name is not None:
            skill = load_skills().get(skill_name)
            if skill is None:
                emit({"type": "error", "message": f"unknown skill: /{skill_name}"})
                return
        user_content = build_turn_message(text, request.ui_state)
        repository.add_message(request.session_id, "user", user_content)
        history = repository.list_messages(request.session_id)
        # In-process web tools are local-API-only: claude gets NATIVE web
        # tools via argv, and cloud APIs (openrouter/custom) stay excluded.
        web_tools_on = request.web_enabled and request.provider in LOCAL_PROVIDERS
        messages = [{"role": "system",
                     "content": build_system_prompt(skill=skill, web_enabled=web_tools_on)},
                    *({"role": m["role"], "content": m["content"]} for m in history)]
        if _provider_type(request.provider) == "cli":
            skill_block = (f"[skill:{skill.name}]\n{skill.instructions}"
                           if skill is not None else "")
            final = cli_turn_fn(
                messages=messages,
                config=CliTurnConfig(
                    provider=request.provider, model=request.model,
                    scratch_base=tool_ctx.repository.db_path.parent,
                    mcp_server_args=_mcp_server_args(request, tool_ctx),
                    db_path=tool_ctx.repository.db_path,
                    web_enabled=request.web_enabled,
                    system_prompt=messages[0]["content"],
                    skill_block=skill_block,
                ),
                session_id=request.session_id,
                prior_session_id=(repository.get_session(request.session_id) or {}).get("cli_session_id"),
                repository=repository, emit=emit,
            )
        else:
            config = ApiTurnConfig(
                api_base=request.api_base, api_key=request.api_key,
                model=request.model,
                native_tools=capability_fn(request.provider, request.api_base,
                                           request.model),
                max_tool_iterations=(SKILL_MAX_TOOL_ITERATIONS if skill is not None
                                     else MAX_TOOL_ITERATIONS),
            )
            registry = build_registry(tool_ctx)
            if web_tools_on:
                register_web_tools(registry)
            final = turn_fn(messages=messages, config=config,
                            registry=registry, emit=emit)
        repository.add_message(request.session_id, "assistant", final)
        emit({"type": "done"})
    except Exception as exc:  # noqa: BLE001 - turn thread must never die silently
        _logger.exception("assistant turn failed for session %s", request.session_id)
        emit({"type": "error", "message": str(exc)})
