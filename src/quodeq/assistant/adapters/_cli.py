"""Drive a CLI provider as one chat turn: hardened spawn, live stream, resume + replay."""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from quodeq.assistant.adapters import _stream
from quodeq.assistant.adapters._cli_command import build_turn_argv
from quodeq.assistant.adapters._cli_config import load_cli_chat_config
from quodeq.assistant.adapters._cli_spawn import (
    build_chat_env, external_sandbox_prefix, scratch_cwd, spawn_turn)
from quodeq.assistant.adapters._linereader import iter_lines
from quodeq.assistant.cancel import CancelToken, TurnCancelled
from quodeq.assistant.mcp import _config as mcp_config
from quodeq.data.ports.assistant import AssistantStore
from quodeq.shared._process_kill import kill_proc_tree as _kill_proc_tree

_logger = logging.getLogger(__name__)

TURN_TIMEOUT_S = 300
_BENIGN_RAW_LINES = (
    "Reading additional input from stdin",
    "WARNING: proceeding, even though we could not create PATH aliases",
)


@dataclass(frozen=True)
class CliTurnConfig:
    provider: str
    model: str | None
    scratch_base: Path
    mcp_server_args: list[str]
    db_path: Path
    web_enabled: bool = False
    system_prompt: str = ""
    skill_block: str = ""
    worktree_dir: Path | None = None


def _latest_user(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m["role"] == "user":
            return m["content"]
    return ""


def _full_transcript(messages: list[dict]) -> str:
    # system + all prior turns collapsed into one prompt for a fresh (no-resume) run
    return "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in messages)


def _raw_error_line(line: str) -> str | None:
    text = line.strip()
    if not text:
        return None
    if any(text.startswith(prefix) for prefix in _BENIGN_RAW_LINES):
        return None
    return text


def _setup_mcp_config(cfg: CliTurnConfig, cli_cfg) -> tuple[str | None, str | None]:
    """Wire the MCP server into the CLI invocation, per provider style.

    Returns ``(mcp_config_path, mcp_config_arg)``; exactly one is set (or
    neither, for ``cli-register``). Runs OUTSIDE ``_run_once``'s try/finally:
    a failure here precedes any resource that needs cleanup.
    """
    if cli_cfg.mcp_style == "config-file":
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        tmp.close()
        mcp_config.write_mcp_config(cfg.mcp_server_args, Path(tmp.name))
        return tmp.name, None
    if cli_cfg.mcp_style == "config-arg":
        # codex: define the server inline per invocation; no global state to clean up.
        return None, mcp_config.codex_mcp_config_arg(cfg.mcp_server_args)
    mcp_config.register_cli_mcp(cli_cfg.cmd, cfg.mcp_server_args,
                                separator=cli_cfg.mcp_add_separator)
    return None, None


def _consume_stream_events(stdout, emit: Callable[[dict], None], parsed_sid: str | None):
    """Drain the CLI's event stream, emitting token/tool_call frames as they
    arrive. Returns the raw pieces ``_finalize_turn_result`` assembles.
    """
    texts, errors, raw_errors = [], [], []
    last_full = None  # text of the last complete message, emitted or not
    partial_buf = ""  # delta text streamed since the last complete message
    saw_result = False
    for line in iter_lines(stdout):
        event = _stream.parse_line(line)
        if event is None:
            raw = _raw_error_line(line)
            if raw:
                raw_errors.append(raw)
            continue
        etype = event.get("type")
        if etype == "result":
            saw_result = True
        err = _stream.error_message(event)
        if err:
            errors.append(err)
        delta = _stream.partial_text(event)
        if delta:
            partial_buf += delta
            emit({"type": "token", "text": delta})
        event_texts = _stream.assistant_text(event)
        if event_texts:
            texts.extend(event_texts)
            # complete events echo text the drawer already shows (an
            # `assistant`/`result` message repeats streamed deltas). Gate on
            # content, not presence, so a differing echo still emits.
            joined = "".join(event_texts)
            is_echo = (joined == partial_buf
                       or (etype == "result" and joined == last_full))
            if not is_echo:
                for t in event_texts:
                    emit({"type": "token", "text": t})
            last_full = joined
            partial_buf = ""
        for tu in _stream.tool_use_details(event):
            frame = {"type": "tool_call", "name": tu["name"]}
            if tu["args_summary"]:
                frame["argsSummary"] = tu["args_summary"]
            emit(frame)
        sid = _stream.session_id(event)
        if sid:
            parsed_sid = sid
    return texts, errors, raw_errors, parsed_sid, partial_buf, saw_result


def _spawn_and_stream(cfg: CliTurnConfig, cli_cfg, spec, *, emit: Callable[[dict], None],
                      spawn_fn, cancel: CancelToken):
    """Build the sandboxed argv, spawn the CLI, and stream its output.

    Returns ``(cwd, proc, timer, sandbox_cleanup, stream_result)`` — the
    first four feed ``_run_once``'s ``finally`` cleanup.
    """
    cwd = scratch_cwd(cfg.scratch_base)
    argv = spec.argv
    sandbox_cleanup = None
    if cli_cfg.requires_external_sandbox:
        # codex needs its internal sandbox bypassed for MCP to work; wrap it
        # in an OS sandbox WE control that blocks writes outside the scratch
        # cwd, temp, ~/.codex, and the assistant db (which draft_action writes).
        db = str(cfg.db_path)
        prefix, sandbox_cleanup = external_sandbox_prefix(
            writable_dirs=[str(cwd), str(Path.home() / ".codex"),
                           *([str(cfg.worktree_dir)] if cfg.worktree_dir else [])],
            writable_files=[db, db + "-wal", db + "-shm", db + "-journal"])
        argv = prefix + argv
    proc = spawn_fn(argv, cwd=cwd, env=build_chat_env())
    # wall-clock guard: a hung/silent CLI can't wedge the turn slot forever
    timer = threading.Timer(TURN_TIMEOUT_S, lambda: _kill_proc_tree(proc))
    timer.start()
    # Stop endpoint: cancelling the token kills the process tree, which
    # EOFs stdout below and lets the turn unwind (runs immediately if the
    # stop already landed).
    cancel.register_kill(lambda: _kill_proc_tree(proc))
    stream_result = _consume_stream_events(proc.stdout, emit, spec.session_id)
    return cwd, proc, timer, sandbox_cleanup, stream_result


def _finalize_turn_result(proc, stream_result, *, repository: AssistantStore, session_id: str
                          ) -> tuple[str, str | None, int, str | None, str | None]:
    texts, errors, raw_errors, parsed_sid, partial_buf, saw_result = stream_result
    try:
        returncode = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _kill_proc_tree(proc)
        returncode = proc.wait()
    # a turn killed mid-message (stop/timeout) streamed deltas that never
    # got their complete-message echo; they are the answer the user saw.
    if partial_buf:
        texts.append(partial_buf)
    # argv-append/result providers (claude) end with a `result` event that
    # echoes the complete answer, so the last text IS the whole reply.
    # streaming-only providers (codex) never send `result`; their answer is
    # the concatenation of every agent_message chunk, not just the last.
    if saw_result:
        final = texts[-1] if texts else ""
    else:
        final = "\n\n".join(texts)
    if parsed_sid:
        repository.set_cli_session_id(session_id, parsed_sid)
    # structured errors (error/turn.failed events) mean the turn genuinely
    # failed; raw stderr lines are often benign warnings. Keep them apart so
    # the caller can raise the former even when partial text was streamed.
    structured_error = errors[0] if errors else None
    raw_error = raw_errors[0] if raw_errors else None
    return final, parsed_sid, returncode, structured_error, raw_error


def _run_once(cfg: CliTurnConfig, cli_cfg, *, prompt: str, session_id: str,
              prior_session_id: str | None, new_session_id: str,
              repository: AssistantStore, emit: Callable[[dict], None],
              spawn_fn, cancel: CancelToken) -> tuple[str, str | None, int, str | None, str | None]:
    mcp_config_path, mcp_config_arg = _setup_mcp_config(cfg, cli_cfg)
    proc = None
    timer = None
    cwd = None
    sandbox_cleanup = None
    try:
        # argv-append providers get the system prompt every run; on the
        # rebuild-replay path the transcript also carries a [system] block,
        # a rare accepted duplication.
        spec = build_turn_argv(cli_cfg, prompt=prompt, model=cfg.model,
                               mcp_config_path=mcp_config_path,
                               prior_session_id=prior_session_id, new_session_id=new_session_id,
                               web_enabled=cfg.web_enabled,
                               system_prompt=cfg.system_prompt,
                               mcp_config_arg=mcp_config_arg)
        cwd, proc, timer, sandbox_cleanup, stream_result = _spawn_and_stream(
            cfg, cli_cfg, spec, emit=emit, spawn_fn=spawn_fn, cancel=cancel)
        return _finalize_turn_result(proc, stream_result, repository=repository,
                                     session_id=session_id)
    finally:
        if timer is not None:
            timer.cancel()
        if proc is not None and proc.poll() is None:
            _kill_proc_tree(proc)
        if mcp_config_path:
            Path(mcp_config_path).unlink(missing_ok=True)
        if sandbox_cleanup is not None:
            sandbox_cleanup()
        if cli_cfg.mcp_style == "cli-register":
            mcp_config.unregister_cli_mcp(cli_cfg.cmd)
        if cwd is not None:
            shutil.rmtree(cwd, ignore_errors=True)


def _inject_system_prompt(cli_cfg, config: CliTurnConfig, prior_session_id: str | None,
                          prompt: str) -> str:
    if cli_cfg.system_prompt_style != "message-prefix":
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


def run_cli_turn(*, messages: list[dict], config: CliTurnConfig, session_id: str,
                 prior_session_id: str | None, repository: AssistantStore,
                 emit: Callable[[dict], None], spawn_fn=None,
                 cancel: CancelToken | None = None) -> str:
    spawn_fn = spawn_fn or spawn_turn
    cancel = cancel or CancelToken()
    if cancel.cancelled:  # stop landed before the turn even spawned
        raise TurnCancelled("")
    cli_cfg = load_cli_chat_config(config.provider)
    prompt = _inject_system_prompt(cli_cfg, config, prior_session_id, _latest_user(messages))
    final, _sid, _rc, structured_error, raw_error = _run_once(
        config, cli_cfg, prompt=prompt, session_id=session_id,
        prior_session_id=prior_session_id, new_session_id=str(uuid.uuid4()),
        repository=repository, emit=emit, spawn_fn=spawn_fn, cancel=cancel)
    # A stopped turn is neither a failure nor a rebuild trigger: the kill
    # leaves empty/partial output and often a nonzero exit, all of which the
    # paths below would misread (rebuilding would RERUN the turn the user
    # just stopped). Unwind with whatever text already streamed.
    if cancel.cancelled:
        raise TurnCancelled(final)
    # rebuild from the full transcript when a resumed turn came back empty, or
    # when it reported a structured failure (a partial answer before an explicit
    # error is not trustworthy). A non-empty answer with only a benign non-zero
    # exit is still success.
    if prior_session_id is not None and (final == "" or structured_error):
        emit({"type": "warning", "message": "session rebuilt"})
        final, _sid, _rc, structured_error, raw_error = _run_once(
            config, cli_cfg, prompt=_full_transcript(messages), session_id=session_id,
            prior_session_id=None, new_session_id=str(uuid.uuid4()),
            repository=repository, emit=emit, spawn_fn=spawn_fn, cancel=cancel)
        if cancel.cancelled:
            raise TurnCancelled(final)
    if structured_error:
        raise RuntimeError(structured_error)
    if final == "":
        raise RuntimeError(raw_error or "CLI produced no output")
    return final
