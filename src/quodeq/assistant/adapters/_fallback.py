"""Prompted-JSON tool-calling contract for models without native tools."""
from __future__ import annotations

import json
import re

FALLBACK_CONTRACT = (
    "\n\n# Tool calling\n"
    "You cannot call functions natively. To use a tool, reply with ONLY a JSON "
    'object: {"tool_call": {"name": "<tool>", "arguments": {...}}} — no other '
    "text. The tool result will arrive in the next user message. When you have "
    "enough information, answer normally without a tool_call object."
)


def fallback_contract(tools: list[dict]) -> str:
    """The contract plus the actual tool catalog (names + argument schemas).

    Native-tools providers get the schemas via the API's `tools` parameter;
    prompted-JSON models otherwise never see a tool name or argument shape and
    must guess them from prose, burning a full generation on every rejected
    call (worst for draft_action, whose payload is validated strictly).
    """
    lines = []
    for tool in tools:
        fn = tool["function"]
        schema = json.dumps(fn.get("parameters") or {}, ensure_ascii=False)
        lines.append(f"- {fn['name']}: {fn['description']}\n  arguments schema: {schema}")
    if not lines:
        return FALLBACK_CONTRACT
    return FALLBACK_CONTRACT + "\n\n# Available tools\n" + "\n".join(lines)

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_prompted_tool_call(text: str) -> tuple[str, dict] | None:
    candidates = _JSON_BLOCK.findall(text)
    stripped = text.strip()
    if stripped.startswith("{"):
        candidates.append(stripped)
    for raw in candidates:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        call = obj.get("tool_call") if isinstance(obj, dict) else None
        if isinstance(call, dict) and isinstance(call.get("name"), str):
            return call["name"], call.get("arguments") or {}
    return None
