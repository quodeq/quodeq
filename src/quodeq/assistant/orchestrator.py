"""Turn lifecycle: persist → contextualize → run adapter → persist → emit."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from quodeq.assistant._context import build_system_prompt, build_turn_message
from quodeq.assistant.adapters._api import ApiTurnConfig, run_api_turn
from quodeq.assistant.adapters._capabilities import supports_native_tools
from quodeq.assistant.skills import load_skills
from quodeq.assistant.tools import ToolContext, build_registry
from quodeq.data.sqlite.assistant_repository import AssistantRepository

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


def _split_skill(text: str):
    if not text.startswith("/"):
        return None, text
    name, _, rest = text[1:].partition(" ")
    return name, rest.strip()


def run_turn(request: TurnRequest, *, repository: AssistantRepository,
             tool_ctx: ToolContext, turn_fn=None, capability_fn=None) -> None:
    turn_fn = turn_fn or run_api_turn
    capability_fn = capability_fn or supports_native_tools
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
        messages = [{"role": "system", "content": build_system_prompt(skill=skill)},
                    *({"role": m["role"], "content": m["content"]} for m in history)]
        config = ApiTurnConfig(
            api_base=request.api_base, api_key=request.api_key,
            model=request.model,
            native_tools=capability_fn(request.provider, request.api_base,
                                       request.model),
        )
        final = turn_fn(messages=messages, config=config,
                        registry=build_registry(tool_ctx), emit=emit)
        repository.add_message(request.session_id, "assistant", final)
        emit({"type": "done"})
    except Exception as exc:  # noqa: BLE001 - turn thread must never die silently
        _logger.exception("assistant turn failed for session %s", request.session_id)
        emit({"type": "error", "message": str(exc)})
