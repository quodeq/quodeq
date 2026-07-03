"""System-prompt and per-turn context assembly."""
from __future__ import annotations

import json
import os
from pathlib import Path

from quodeq.assistant.skills import Skill

_CONTEXT_PATH = Path(
    os.environ.get(
        "QUODEQ_ASSISTANT_CONTEXT_PATH",
        str(Path(__file__).resolve().parent.parent / "data" / "assistant"
            / "quodeq_context.md"),
    )
)


def build_system_prompt(skill: Skill | None = None) -> str:
    prompt = _CONTEXT_PATH.read_text(encoding="utf-8")
    if skill is not None:
        prompt += f"\n\n# Active skill: {skill.name}\n{skill.instructions}"
    return prompt


def build_turn_message(text: str, ui_state: dict | None) -> str:
    if not ui_state:
        return text
    return f"[ui-state] {json.dumps(ui_state, ensure_ascii=False)}\n\n{text}"
