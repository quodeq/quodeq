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
from quodeq.assistant.mcp import _config as mcp_config
from quodeq.data.sqlite.assistant_repository import AssistantRepository
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


def _run_once(cfg: CliTurnConfig, cli_cfg, *, prompt: str, session_id: str,
              prior_session_id: str | None, new_session_id: str,
              repository: AssistantRepository, emit: Callable[[dict], None],
              spawn_fn) -> tuple[str, str | None, int, str | None, str | None]:
    mcp_config_path = None
    mcp_config_arg = None
    if cli_cfg.mcp_style == "config-file":
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        tmp.close()
        mcp_config_path = tmp.name
        mcp_config.write_mcp_config(cfg.mcp_server_args, Path(mcp_config_path))
    elif cli_cfg.mcp_style == "config-arg":
        # codex: define the server inline per invocation; no global state to clean up.
        mcp_config_arg = mcp_config.codex_mcp_config_arg(cfg.mcp_server_args)
    else:
        mcp_config.register_cli_mcp(cli_cfg.cmd, cfg.mcp_server_args,
                                    separator=cli_cfg.mcp_add_separator)
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
        cwd = scratch_cwd(cfg.scratch_base)
        argv = spec.argv
        if cli_cfg.requires_external_sandbox:
            # codex needs its internal sandbox bypassed for MCP to work; wrap it
            # in an OS sandbox WE control that blocks writes outside the scratch
            # cwd, temp, ~/.codex, and the assistant db (which draft_action writes).
            db = str(cfg.db_path)
            prefix, sandbox_cleanup = external_sandbox_prefix(
                writable_dirs=[str(cwd), str(Path.home() / ".codex")],
                writable_files=[db, db + "-wal", db + "-shm", db + "-journal"])
            argv = prefix + argv
        proc = spawn_fn(argv, cwd=cwd, env=build_chat_env())
        # wall-clock guard: a hung/silent CLI can't wedge the turn slot forever
        timer = threading.Timer(TURN_TIMEOUT_S, lambda: _kill_proc_tree(proc))
        timer.start()
        texts, errors, raw_errors, parsed_sid = [], [], [], spec.session_id
        last_emitted = None
        saw_result = False
        for line in iter_lines(proc.stdout):
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
            for t in _stream.assistant_text(event):
                texts.append(t)
                # the final `result` event echoes the full text already streamed
                # via `assistant`/`item.completed` events; skip re-emitting it so
                # the drawer doesn't show the answer twice. Gate on content, not
                # presence: a `result` whose text DIFFERS from what was streamed
                # (or a result-only turn) must still be emitted.
                if etype == "result" and t == last_emitted:
                    continue
                emit({"type": "token", "text": t})
                last_emitted = t
            for tu in _stream.tool_use_details(event):
                frame = {"type": "tool_call", "name": tu["name"]}
                if tu["args_summary"]:
                    frame["argsSummary"] = tu["args_summary"]
                emit(frame)
            sid = _stream.session_id(event)
            if sid:
                parsed_sid = sid
        try:
            returncode = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _kill_proc_tree(proc)
            returncode = proc.wait()
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


def run_cli_turn(*, messages: list[dict], config: CliTurnConfig, session_id: str,
                 prior_session_id: str | None, repository: AssistantRepository,
                 emit: Callable[[dict], None], spawn_fn=None) -> str:
    spawn_fn = spawn_fn or spawn_turn
    cli_cfg = load_cli_chat_config(config.provider)
    prompt = _latest_user(messages)
    if cli_cfg.system_prompt_style == "message-prefix":
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
            prompt = "\n\n".join([*parts, prompt])
    final, _sid, _rc, structured_error, raw_error = _run_once(
        config, cli_cfg, prompt=prompt, session_id=session_id,
        prior_session_id=prior_session_id, new_session_id=str(uuid.uuid4()),
        repository=repository, emit=emit, spawn_fn=spawn_fn)
    # rebuild from the full transcript when a resumed turn came back empty, or
    # when it reported a structured failure (a partial answer before an explicit
    # error is not trustworthy). A non-empty answer with only a benign non-zero
    # exit is still success.
    if prior_session_id is not None and (final == "" or structured_error):
        emit({"type": "warning", "message": "session rebuilt"})
        final, _sid, _rc, structured_error, raw_error = _run_once(
            config, cli_cfg, prompt=_full_transcript(messages), session_id=session_id,
            prior_session_id=None, new_session_id=str(uuid.uuid4()),
            repository=repository, emit=emit, spawn_fn=spawn_fn)
    if structured_error:
        raise RuntimeError(structured_error)
    if final == "":
        raise RuntimeError(raw_error or "CLI produced no output")
    return final
