"""draft_action: the model's only write primitive, server-canonical drafts."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from flask import Flask

from quodeq.assistant.tools._context import ToolContext
from quodeq.assistant.tools._registry import ToolError, ToolRegistry, ToolSpec
from quodeq.services.import_validator import validate_import


class ActionConflict(Exception):
    """Apply-time domain conflict; the endpoint maps it to HTTP 409."""


@dataclass(frozen=True)
class ActionSpec:
    action_type: str
    description: str
    validate: Callable[[dict, ToolContext], dict]  # raises ToolError / returns canonical payload
    summarize: Callable[[dict], dict]              # server-canonical card summary fields
    apply: Callable[[dict, Flask], dict]           # executes on user approval


def _validate_create_standard(payload: dict, ctx: ToolContext) -> dict:
    verdict = validate_import(payload)
    if not verdict["valid"]:
        raise ToolError("invalid standard payload: " + "; ".join(verdict["errors"]))
    return verdict["data"]


def _summarize_create_standard(canonical: dict) -> dict:
    return {
        "id": canonical.get("id"), "name": canonical.get("name"),
        "principleCount": len(canonical.get("principles", [])),
    }


def _apply_create_standard(payload: dict, app: Flask) -> dict:
    from quodeq.services.standards import StandardsService  # noqa: PLC0415

    service = StandardsService(
        Path(app.config["STANDARDS_EVALUATORS_DIR"]),
        Path(app.config["STANDARDS_COMPILED_DIR"]),
        Path(app.config["STANDARDS_DIMENSIONS_FILE"]),
    )
    result = service.import_from_file(payload, force=False)
    if result.get("status") == "conflict":
        raise ActionConflict("standard id already exists")
    return result


ACTIONS: dict[str, ActionSpec] = {
    "create_standard": ActionSpec(
        action_type="create_standard",
        description="Draft a new custom standard. Applied only after you approve the preview card.",
        validate=_validate_create_standard,
        summarize=_summarize_create_standard,
        apply=_apply_create_standard,
    ),
}

# Derived views kept for the catalog route and existing imports.
ACTION_TYPES = frozenset(ACTIONS)
ACTION_DESCRIPTIONS = {t: s.description for t, s in ACTIONS.items()}


def _draft_action(ctx: ToolContext, action_type: str, payload: dict) -> dict:
    spec = ACTIONS.get(action_type)
    if spec is None:
        raise ToolError(f"unsupported action type: {action_type}")
    canonical = spec.validate(payload, ctx)
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
        "summary": spec.summarize(canonical),
    })
    return {"action_id": action_id, "status": "drafted", "action_type": action_type}


def register_action_tools(registry: ToolRegistry, ctx: ToolContext) -> None:
    registry.register(ToolSpec(
        "draft_action",
        "Draft an action for the user to review and apply. The draft is shown "
        "to the user as a preview card; nothing is written until they approve. "
        "Payloads by type: create_standard takes a full standard JSON.",
        {"type": "object", "properties": {
            "action_type": {"type": "string", "enum": sorted(ACTION_TYPES)},
            "payload": {"type": "object"},
        }, "required": ["action_type", "payload"]},
        lambda **kw: _draft_action(ctx, **kw)))
