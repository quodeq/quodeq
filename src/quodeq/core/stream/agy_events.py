"""Antigravity CLI (agy) stream events, recast in the shape the parsers read.

``agy --output-format stream-json`` keys its events by ``event`` (``init``,
``step_update``, ``result``) where every other CLI Quodeq drives keys them by
``type``. Rather than teach each parser a fifth dialect, one event is mapped
here to the Claude-shaped event that carries the same meaning: a text delta
becomes a ``stream_event`` text delta, a tool step an ``assistant`` tool_use
block (``Read`` for file reads, ``mcp__<server>__<tool>`` for MCP calls) and
its end a ``user`` tool_result, the final ``result`` a ``result`` with the
answer text and the conversation id as ``session_id``. Pure dict handling.
"""
from __future__ import annotations

import re

_AGY_EVENT_KEY = "event"
_INIT, _STEP, _RESULT = "init", "step_update", "result"
_STEP_AGENT_RESPONSE = "agent_response"
_STEP_TOOL = "tool"
_STATE_ACTIVE = "ACTIVE"
_STATE_ERROR = "ERROR"
_STATUS_SUCCESS = "SUCCESS"
_TOOL_READ_FILE = "read_file"
_TOOL_CALL_MCP = "call_mcp_tool"
# An always-loaded MCP tool runs under its own name, mcp_<server>_<tool>;
# Quodeq's server names have no underscore, so the first one splits them.
_DIRECT_MCP = re.compile(r"mcp_([^_]+)_(.+)")


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def is_agy_event(event: object) -> bool:
    """Whether *event* is in agy's own ``event``-keyed dialect."""
    return (isinstance(event, dict) and "type" not in event
            and isinstance(event.get(_AGY_EVENT_KEY), str))


def _tool_name_and_input(step: dict) -> tuple[str, object]:
    info = _dict(step.get("tool_info"))
    params = _dict(info.get("parameters"))
    name = step.get("tool_name") or info.get("name") or _STEP_TOOL
    if name == _TOOL_READ_FILE:
        return "Read", {"file_path": params.get("Path")}
    if name == _TOOL_CALL_MCP:
        return f"mcp__{params.get('ServerName')}__{params.get('ToolName')}", params.get("Arguments")
    if direct := _DIRECT_MCP.fullmatch(str(name)):
        return f"mcp__{direct[1]}__{direct[2]}", params
    return str(name), params


def _from_step(step: dict) -> dict:
    if step.get("step_type") == _STEP_AGENT_RESPONSE:
        text = step.get("text_delta")
        if not isinstance(text, str) or not text:
            return {"type": "agy.step"}
        return {"type": "stream_event", "event": {
            "type": "content_block_delta", "delta": {"type": "text_delta", "text": text}}}
    if step.get("step_type") != _STEP_TOOL:
        return {"type": "agy.step"}
    call_id = f"agy-step-{step.get('step_index')}"
    if step.get("state") == _STATE_ACTIVE:
        name, tool_input = _tool_name_and_input(step)
        return {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": call_id, "name": name, "input": tool_input}]}}
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": call_id,
         "is_error": step.get("state") == _STATE_ERROR}]}}


def _from_result(result: dict) -> dict:
    response = result.get("response")
    return {
        "type": "result",
        "result": response if isinstance(response, str) else "",
        "session_id": result.get("conversation_id"),
        "is_error": result.get("status") != _STATUS_SUCCESS,
        "denied_actions": result.get("denied_actions") or [],
    }


def normalize_event(event: object) -> object:
    """*event* in the Claude shape when it is an agy event, else unchanged."""
    if not is_agy_event(event):
        return event
    kind = event[_AGY_EVENT_KEY]
    if kind == _INIT:
        return {"type": "system", "subtype": "init", "session_id": event.get("conversation_id")}
    if kind == _STEP:
        return _from_step(_dict(event.get(_STEP)))
    if kind == _RESULT:
        return _from_result(_dict(event.get(_RESULT)))
    return {"type": f"agy.{kind}"}
