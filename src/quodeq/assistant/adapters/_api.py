"""Streaming multi-turn tool loop over any OpenAI-compatible endpoint."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Callable

import queue
import threading

import httpx
import openai

from quodeq.assistant.adapters._fallback import (
    extract_prompted_tool_call,
    fallback_contract,
)
from quodeq.assistant.cancel import CancelToken, TurnCancelled
from quodeq.assistant.guard import MAX_TOOL_ITERATIONS, guard_tool_result
from quodeq.assistant.tools._registry import ToolRegistry

_logger = logging.getLogger(__name__)
_TIMEOUT = httpx.Timeout(connect=10.0, read=500.0, write=30.0, pool=10.0)
_CAP_NOTE = "\n\n*(stopped: tool iteration limit reached)*"
_OPENAI_API_HOST = "api.openai.com"


def _extra_body(config: "ApiTurnConfig") -> dict:
    """Provider tuning that mirrors the analysis API runner so the assistant
    behaves like the (working) evaluation path on the same local models.

    Local reasoning models (Gemma, Qwen3) otherwise burn thousands of thinking
    tokens before answering — a multi-minute streamed generation that is prone
    to dropped connections ("Connection error"). Disabling chat-template
    thinking keeps them fast. `num_ctx` mirrors the analysis path but only
    reaches non-Ollama providers: Ollama's /v1 endpoint ignores per-request
    num_ctx, so there the model's context comes from the server setting.
    """
    body: dict = {}
    # Ollama only honours `reasoning_effort`; `chat_template_kwargs` is the
    # llama.cpp/vLLM knob. Local providers get both (see _api_runner).
    body["reasoning_effort"] = "none"
    if _OPENAI_API_HOST not in (config.api_base or ""):
        body["chat_template_kwargs"] = {"enable_thinking": False}
    env_ctx = os.environ.get("QUODEQ_CONTEXT_SIZE", "").strip()
    if env_ctx.isdigit() and int(env_ctx) > 0:
        body["num_ctx"] = int(env_ctx)
    return body


@dataclass(frozen=True)
class ApiTurnConfig:
    api_base: str
    api_key: str | None
    model: str
    native_tools: bool
    max_tool_iterations: int = MAX_TOOL_ITERATIONS


# Placeholder the OpenAI SDK requires for local OpenAI-compatible servers
# (Ollama, llama.cpp) that ignore the Authorization header; a configured
# key always wins. Not a credential.
_OLLAMA_DEFAULT_API_KEY = "ollama"


def _default_client(config: ApiTurnConfig):
    return openai.OpenAI(
        base_url=config.api_base,
        api_key=config.api_key or _OLLAMA_DEFAULT_API_KEY,
        timeout=_TIMEOUT,
        max_retries=0,
    )


_STREAM_DONE = object()


def _iter_with_cancel(stream, cancel):
    """Yield `stream`'s chunks while staying cancellable during a BLOCKED read.

    The blocking reads happen in a dedicated daemon reader thread feeding a
    queue; this (turn-thread) side polls the queue with a short timeout and
    checks the token each tick. Closing the HTTP client from another thread
    does NOT reliably wake a thread blocked in a socket read (live-verified on
    macOS: the read hung and the turn slot stayed claimed), so a cancel must
    never depend on another chunk arriving. On cancel the stranded reader is
    abandoned; it holds only the dying connection, not the turn slot.
    """
    # Unbounded so the reader NEVER blocks on put: after a cancel the consumer
    # stops draining, and a blocked put would strand the reader even once the
    # connection finally delivers. Growth is bounded by the post-put check.
    q: queue.Queue = queue.Queue()

    def _read():
        try:
            for chunk in stream:
                q.put(chunk)
                if cancel.cancelled:
                    return  # consumer is gone; stop producing
            q.put(_STREAM_DONE)
        except Exception as exc:  # noqa: BLE001 - delivered to the consumer
            q.put(exc)

    threading.Thread(target=_read, daemon=True).start()
    while True:
        if cancel.cancelled:
            raise TurnCancelled("")
        try:
            item = q.get(timeout=0.25)
        except queue.Empty:
            continue
        if item is _STREAM_DONE:
            return
        if isinstance(item, Exception):
            raise item
        yield item


def _stream_once(client, config, messages, registry, emit, cancel):
    """One streamed completion. Returns (text, tool_calls) where tool_calls is
    a list of {"id", "name", "arguments"} assembled from streamed deltas."""
    kwargs = {"model": config.model, "messages": messages, "stream": True}
    if config.native_tools:
        kwargs["tools"] = registry.openai_tools()
    extra = _extra_body(config)
    if extra:
        kwargs["extra_body"] = extra
    text_parts: list[str] = []
    calls: dict[int, dict] = {}
    try:
        for chunk in _iter_with_cancel(client.chat.completions.create(**kwargs), cancel):
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                text_parts.append(delta.content)
                emit({"type": "token", "text": delta.content})
            for tc in getattr(delta, "tool_calls", None) or []:
                slot = calls.setdefault(tc.index, {"id": None, "name": None, "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    slot["arguments"] += tc.function.arguments
    except Exception:
        # cancel() closes the client to interrupt a stalled read; the read
        # then raises here. That's the stop succeeding, not a turn failure.
        if cancel.cancelled:
            raise TurnCancelled("".join(text_parts)) from None
        raise
    return "".join(text_parts), [calls[i] for i in sorted(calls)]


def _dispatch_tool_calls(
    convo: list[dict],
    tool_calls: list[dict],
    text: str,
    registry: ToolRegistry,
    emit: Callable[[dict], None],
) -> None:
    """Append the assistant tool-call message, then dispatch each call in
    order, appending its tool result. Mutates *convo* in place.

    Order matters: the assistant message (declaring all tool_calls) must be
    appended before any tool-result message, and each call's emit/convo-append
    pair must land before the next call's is dispatched.
    """
    convo.append({"role": "assistant", "content": text or None,
                  "tool_calls": [
                      {"id": c["id"], "type": "function",
                       "function": {"name": c["name"],
                                    "arguments": c["arguments"] or "{}"}}
                      for c in tool_calls]})
    for call in tool_calls:
        arguments = _parse_args(call["arguments"])
        result = registry.dispatch(call["name"], arguments)
        frame = {"type": "tool_call", "name": call["name"], "ok": result["ok"]}
        if _args_summary(arguments):
            frame["argsSummary"] = _args_summary(arguments)
        emit(frame)
        fenced, warnings = guard_tool_result(result, call["name"])
        _emit_warnings(emit, warnings)
        convo.append({"role": "tool", "tool_call_id": call["id"],
                      "content": fenced})


def run_api_turn(*, messages: list[dict], config: ApiTurnConfig,
                 registry: ToolRegistry, emit: Callable[[dict], None],
                 client_factory=None, cancel: CancelToken | None = None) -> str:
    cancel = cancel or CancelToken()
    convo = list(messages)
    if not config.native_tools:
        contract = fallback_contract(registry.openai_tools())
        convo = [dict(convo[0], content=convo[0]["content"] + contract),
                 *convo[1:]] if convo and convo[0]["role"] == "system" else (
            [{"role": "system", "content": contract.strip()}, *convo])
    factory = client_factory or _default_client
    text = ""
    with factory(config) as client:
        # Stop endpoint: closing the client interrupts a blocked/stalled read
        # (e.g. a local model still cold-loading emits no chunks to poll on).
        close = getattr(client, "close", None)
        if close is not None:
            cancel.register_kill(close)
        for _ in range(config.max_tool_iterations):
            if cancel.cancelled:
                raise TurnCancelled(text)
            text, tool_calls = _stream_once(client, config, convo, registry, emit, cancel)
            if cancel.cancelled:
                raise TurnCancelled(text)
            if not config.native_tools:
                prompted = extract_prompted_tool_call(text)
                if prompted is None:
                    return text
                name, arguments = prompted
                result = registry.dispatch(name, arguments)
                frame = {"type": "tool_call", "name": name, "ok": result["ok"]}
                if _args_summary(arguments):
                    frame["argsSummary"] = _args_summary(arguments)
                emit(frame)
                fenced, warnings = guard_tool_result(result, name)
                _emit_warnings(emit, warnings)
                convo.append({"role": "assistant", "content": text})
                convo.append({"role": "user", "content": fenced})
                continue
            if not tool_calls:
                return text
            _dispatch_tool_calls(convo, tool_calls, text, registry, emit)
    return text + _CAP_NOTE


def _args_summary(arguments: dict) -> str:
    return json.dumps(arguments, ensure_ascii=False)[:80] if arguments else ""


def _parse_args(raw: str) -> dict:
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _emit_warnings(emit, warnings):
    for warning in warnings:
        emit({"type": "warning", "message": warning})
