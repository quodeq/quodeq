"""Drive a CLI provider as one chat turn: hardened spawn, live stream, resume + replay."""
from __future__ import annotations

import logging
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, NamedTuple

from quodeq.assistant.adapters._cli_command import (
    McpConfigRef, TurnArgvRequest, build_turn_argv)
from quodeq.assistant.adapters._cli_cleanup import TurnResources, release_turn_resources
from quodeq.assistant.adapters.cli_config import (
    SYSTEM_PROMPT_STYLE_MESSAGE_PREFIX, load_cli_chat_config,
)
from quodeq.assistant.adapters._cli_spawn import (
    build_chat_env, external_sandbox_prefix, scratch_cwd, spawn_turn)
from quodeq.assistant.adapters._cli_events import StreamOutcome, consume_stream_events
from quodeq.assistant.cancel import CancelToken, TurnCancelled
from quodeq.assistant.mcp import mcp_config
from quodeq.core.constants import MCP_STYLE_CONFIG_ARG, MCP_STYLE_CONFIG_FILE
from quodeq.data.ports.assistant import AssistantStore
from quodeq.shared.process_kill import kill_proc_tree as _kill_proc_tree

_logger = logging.getLogger(__name__)

TURN_TIMEOUT_S = 300
_REAPER_WAIT_S = 10  # grace period after stream EOF before force-killing the process tree


@dataclass(frozen=True)
class CliTurnConfig:
    """Per-turn CLI adapter settings (provider, model, scratch, MCP wiring)."""

    provider: str
    model: str | None
    scratch_base: Path
    mcp_server_args: list[str]
    db_path: Path
    web_enabled: bool = False
    system_prompt: str = ""
    skill_block: str = ""
    worktree_dir: Path | None = None


@dataclass(frozen=True)
class CliTurnSession:
    """Per-turn CLI session state (ids, store, event sink, cancellation)."""

    session_id: str
    prior_session_id: str | None
    repository: AssistantStore
    emit: Callable[[dict], None]
    spawn_fn: Callable | None = None
    cancel: CancelToken | None = None


def _latest_user(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m["role"] == "user":
            return m["content"]
    return ""


def _full_transcript(messages: list[dict]) -> str:
    # system + all prior turns collapsed into one prompt for a fresh (no-resume) run
    return "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in messages)


def _setup_mcp_config(cfg: CliTurnConfig, cli_cfg) -> McpConfigRef:
    """Wire the MCP server into the CLI invocation, per provider style.

    Returns an ``McpConfigRef``; exactly one of ``path``/``arg`` is set (or
    neither, for ``cli-register``). Runs OUTSIDE ``_run_once``'s try/finally:
    a failure here precedes any resource that needs cleanup.
    """
    if cli_cfg.mcp_style == MCP_STYLE_CONFIG_FILE:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        tmp.close()
        mcp_config.write_mcp_config(cfg.mcp_server_args, Path(tmp.name), tools=cli_cfg.mcp_server_tools)
        return McpConfigRef(tmp.name, None)
    if cli_cfg.mcp_style == MCP_STYLE_CONFIG_ARG:
        # codex: define the server inline per invocation; no global state to clean up.
        return McpConfigRef(None, mcp_config.codex_mcp_config_arg(cfg.mcp_server_args))
    mcp_config.register_cli_mcp(cli_cfg.cmd, cfg.mcp_server_args,
                                separator=cli_cfg.mcp_add_separator)
    return McpConfigRef(None, None)


def _external_sandbox(cfg: CliTurnConfig, cwd: Path) -> tuple[list[str], object | None]:
    """The OS-sandbox launcher prefix for this turn, and its cleanup handle.

    codex needs its internal sandbox bypassed for MCP to work, so we wrap it
    in an OS sandbox WE control that blocks writes outside the scratch cwd,
    temp, ~/.codex and the assistant db (which draft_action writes).
    """
    db = str(cfg.db_path)
    return external_sandbox_prefix(
        writable_dirs=[str(cwd), str(Path.home() / ".codex"),
                       *([str(cfg.worktree_dir)] if cfg.worktree_dir else [])],
        writable_files=[db, db + "-wal", db + "-shm", db + "-journal"])


def _arm_kill_guards(proc, session: CliTurnSession) -> threading.Timer:
    """Wire the wall-clock timeout and the stop endpoint to the process tree.

    The timer stops a hung or silent CLI from wedging the turn slot forever.
    Cancelling the token kills the same tree, which EOFs stdout and lets the
    turn unwind (it runs immediately if the stop already landed).
    """
    timer = threading.Timer(TURN_TIMEOUT_S, lambda: _kill_proc_tree(proc))
    timer.start()
    session.cancel.register_kill(lambda: _kill_proc_tree(proc))
    return timer


def _spawn_and_stream(cfg: CliTurnConfig, cli_cfg, spec, session: CliTurnSession):
    """Build the sandboxed argv, spawn the CLI, and stream its output.

    Returns ``(cwd, proc, timer, sandbox_cleanup, stream_result)`` — the
    first four feed ``_run_once``'s ``finally`` cleanup. *session* must
    carry resolved ``spawn_fn``/``cancel`` (``run_cli_turn`` fills them in).
    """
    cwd = scratch_cwd(cfg.scratch_base)
    argv = spec.argv
    sandbox_cleanup = None
    if cli_cfg.requires_external_sandbox:
        prefix, sandbox_cleanup = _external_sandbox(cfg, cwd)
        argv = prefix + argv
    proc = session.spawn_fn(argv, cwd=cwd, env=build_chat_env(provider=cfg.provider))
    timer = _arm_kill_guards(proc, session)
    stream_result = consume_stream_events(proc.stdout, session.emit, spec.session_id)
    return cwd, proc, timer, sandbox_cleanup, stream_result


class TurnOutcome(NamedTuple):
    """One completed CLI turn, as the retry/raise logic in run_cli_turn reads it."""

    final: str
    session_id: str | None
    returncode: int
    structured_error: str | None
    raw_error: str | None


def _finalize_turn_result(
    proc, stream: StreamOutcome, *, repository: AssistantStore, session_id: str,
) -> TurnOutcome:
    """Reap the process and fold the stream into the turn's answer and errors."""
    texts = stream.texts
    try:
        returncode = proc.wait(timeout=_REAPER_WAIT_S)
    except subprocess.TimeoutExpired:
        _kill_proc_tree(proc)
        returncode = proc.wait()
    # a turn killed mid-message (stop/timeout) streamed deltas that never
    # got their complete-message echo; they are the answer the user saw.
    if stream.partial_buf:
        texts.append(stream.partial_buf)
    # argv-append/result providers (claude) end with a `result` event that
    # echoes the complete answer, so the last text IS the whole reply.
    # streaming-only providers (codex) never send `result`; their answer is
    # the concatenation of every agent_message chunk, not just the last.
    if stream.saw_result:
        final = texts[-1] if texts else ""
    else:
        final = "\n\n".join(texts)
    if stream.session_id:
        repository.set_cli_session_id(session_id, stream.session_id)
    # structured errors (error/turn.failed events) mean the turn genuinely
    # failed; raw stderr lines are often benign warnings. Keep them apart so
    # the caller can raise the former even when partial text was streamed.
    return TurnOutcome(
        final=final,
        session_id=stream.session_id,
        returncode=returncode,
        structured_error=stream.errors[0] if stream.errors else None,
        raw_error=stream.raw_errors[0] if stream.raw_errors else None,
    )


def _run_once(cfg: CliTurnConfig, cli_cfg, session: CliTurnSession, prompt: str,
              new_session_id: str) -> TurnOutcome:
    mcp_config_ref = _setup_mcp_config(cfg, cli_cfg)
    resources = TurnResources()
    try:
        # argv-append providers get the system prompt every run; on the
        # rebuild-replay path the transcript also carries a [system] block,
        # a rare accepted duplication.
        request = TurnArgvRequest.from_turn_config(
            cfg, prompt=prompt, mcp_config=mcp_config_ref,
            prior_session_id=session.prior_session_id, new_session_id=new_session_id)
        spec = build_turn_argv(cli_cfg, request)
        (resources.cwd, resources.proc, resources.timer, resources.sandbox_cleanup,
         stream_result) = _spawn_and_stream(cfg, cli_cfg, spec, session)
        return _finalize_turn_result(resources.proc, stream_result, repository=session.repository,
                                     session_id=session.session_id)
    finally:
        release_turn_resources(resources, mcp_config_ref=mcp_config_ref, cli_cfg=cli_cfg)


def _inject_system_prompt(cli_cfg, config: CliTurnConfig, prior_session_id: str | None,
                          prompt: str) -> str:
    if cli_cfg.system_prompt_style != SYSTEM_PROMPT_STYLE_MESSAGE_PREFIX:
        return prompt
    # argv-append providers (claude) carry the system prompt + skill inside
    # --append-system-prompt every run. message-prefix providers (codex,
    # gemini) have no such flag, so we inline them into the message. The base
    # system prompt goes only on the first turn of a session (prior_session_id
    # is None); session resume carries it forward, and a lost/unparsed session
    # id re-triggers injection. The skill block rides every turn because it can
    # change mid-conversation.
    parts = []
    if config.system_prompt and prior_session_id is None:
        parts.append(config.system_prompt)
    if config.skill_block:
        parts.append(config.skill_block)
    if parts:
        return "\n\n".join([*parts, prompt])
    return prompt


def run_cli_turn(*, messages: list[dict], config: CliTurnConfig,
                 session: CliTurnSession) -> str:
    """Run one assistant turn through the provider CLI and return its answer.

    Args:
        messages: The conversation so far; the last user message is the
            prompt, and the whole transcript is replayed if the turn has to
            be rebuilt.
        config: Provider, paths and prompt blocks for this turn.
        session: The repository, emit callback and cancel token, plus the
            prior CLI session id to resume from (None starts fresh).

    Returns:
        The assistant's answer text.

    Raises:
        TurnCancelled: The stop endpoint fired; the partial answer rides on
            the exception.
        RuntimeError: The CLI reported a structured error or produced no
            output at all.
    """
    session = replace(session, spawn_fn=session.spawn_fn or spawn_turn,
                      cancel=session.cancel or CancelToken())
    if session.cancel.cancelled:  # stop landed before the turn even spawned
        raise TurnCancelled("")
    cli_cfg = load_cli_chat_config(config.provider)
    prompt = _inject_system_prompt(cli_cfg, config, session.prior_session_id,
                                   _latest_user(messages))
    outcome = _run_once(config, cli_cfg, session, prompt, str(uuid.uuid4()))
    # A stopped turn is neither a failure nor a rebuild trigger: the kill
    # leaves empty/partial output and often a nonzero exit, all of which the
    # paths below would misread (rebuilding would RERUN the turn the user
    # just stopped). Unwind with whatever text already streamed.
    if session.cancel.cancelled:
        raise TurnCancelled(outcome.final)
    # rebuild from the full transcript when a resumed turn came back empty, or
    # when it reported a structured failure (a partial answer before an explicit
    # error is not trustworthy). A non-empty answer with only a benign non-zero
    # exit is still success.
    if session.prior_session_id is not None and (outcome.final == "" or outcome.structured_error):
        session.emit({"type": "warning", "message": "session rebuilt"})
        outcome = _run_once(
            config, cli_cfg, replace(session, prior_session_id=None),
            _full_transcript(messages), str(uuid.uuid4()))
        if session.cancel.cancelled:
            raise TurnCancelled(outcome.final)
    if outcome.structured_error:
        raise RuntimeError(outcome.structured_error)
    if outcome.final == "":
        raise RuntimeError(outcome.raw_error or "CLI produced no output")
    return outcome.final
