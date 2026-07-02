"""draft_action: the model's only write primitive — server-canonical drafts."""
from __future__ import annotations

import hashlib
import json
import uuid

from quodeq.assistant.tools._context import ToolContext
from quodeq.assistant.tools._registry import ToolError, ToolRegistry, ToolSpec
from quodeq.services.import_validator import validate_import

ACTION_TYPES = frozenset({"create_standard"})


def _draft_action(ctx: ToolContext, action_type: str, payload: dict) -> dict:
    if action_type not in ACTION_TYPES:
        raise ToolError(f"unsupported action type: {action_type}")
    verdict = validate_import(payload)
    if not verdict["valid"]:
        raise ToolError("invalid standard payload: " + "; ".join(verdict["errors"]))
    canonical = verdict["data"]
    action_id = uuid.uuid4().hex
    content_hash = hashlib.sha256(
        json.dumps(canonical, sort_keys=True).encode("utf-8")
    ).hexdigest()
    ctx.repository.create_action(
        action_id=action_id, session_id=ctx.session_id,
        action_type=action_type, payload=canonical, content_hash=content_hash,
    )
    ctx.repository.append_event(ctx.session_id, {
        "type": "action_draft", "actionId": action_id, "actionType": action_type,
        "summary": {
            "id": canonical.get("id"), "name": canonical.get("name"),
            "principleCount": len(canonical.get("principles", [])),
        },
    })
    return {"action_id": action_id, "status": "drafted", "action_type": action_type}


def register_action_tools(registry: ToolRegistry, ctx: ToolContext) -> None:
    registry.register(ToolSpec(
        "draft_action",
        "Draft an action for the user to review and apply. The draft is shown "
        "to the user as a preview card; nothing is written until they approve.",
        {"type": "object", "properties": {
            "action_type": {"type": "string", "enum": sorted(ACTION_TYPES)},
            "payload": {"type": "object"},
        }, "required": ["action_type", "payload"]},
        lambda **kw: _draft_action(ctx, **kw)))
