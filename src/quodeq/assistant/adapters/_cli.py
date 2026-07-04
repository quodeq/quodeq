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
from quodeq.assistant.adapters._cli_spawn import build_chat_env, scratch_cwd, spawn_turn
from quodeq.assistant.adapters._linereader import iter_lines
from quodeq.assistant.mcp import _config as mcp_config
from quodeq.data.sqlite.assistant_repository import AssistantRepository
from quodeq.shared._process_kill import kill_proc_tree as _kill_proc_tree

_logger = logging.getLogger(__name__)

TURN_TIMEOUT_S = 300


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


def _run_once(cfg: CliTurnConfig, cli_cfg, *, prompt: str, session_id: str,
              prior_session_id: str | None, new_session_id: str,
              repository: AssistantRepository, emit: Callable[[dict], None],
              spawn_fn) -> tuple[str, str | None, int]:
    mcp_config_path = None
    if cli_cfg.mcp_style == "config-file":
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        tmp.close()
        mcp_config_path = tmp.name
        mcp_config.write_mcp_config(cfg.mcp_server_args, Path(mcp_config_path))
    else:
        mcp_config.register_cli_mcp(cli_cfg.cmd, cfg.mcp_server_args,
                                    separator=cli_cfg.mcp_add_separator)
    proc = None
    timer = None
    cwd = None
    try:
        # argv-append providers get the system prompt every run; on the
        # rebuild-replay path the transcript also carries a [system] block,
        # a rare accepted duplication.
        spec = build_turn_argv(cli_cfg, prompt=prompt, model=cfg.model,
                               mcp_config_path=mcp_config_path,
                               prior_session_id=prior_session_id, new_session_id=new_session_id,
                               web_enabled=cfg.web_enabled,
                               system_prompt=cfg.system_prompt)
        cwd = scratch_cwd(cfg.scratch_base)
        proc = spawn_fn(spec.argv, cwd=cwd, env=build_chat_env())
        # wall-clock guard: a hung/silent CLI can't wedge the turn slot forever
        timer = threading.Timer(TURN_TIMEOUT_S, lambda: _kill_proc_tree(proc))
        timer.start()
        texts, parsed_sid = [], spec.session_id
        last_emitted = None
        for line in iter_lines(proc.stdout):
            event = _stream.parse_line(line)
            if event is None:
                continue
            etype = event.get("type")
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
        final = texts[-1] if texts else ""
        if parsed_sid:
            repository.set_cli_session_id(session_id, parsed_sid)
        return final, parsed_sid, returncode
    finally:
        if timer is not None:
            timer.cancel()
        if proc is not None and proc.poll() is None:
            _kill_proc_tree(proc)
        if mcp_config_path:
            Path(mcp_config_path).unlink(missing_ok=True)
        if cli_cfg.mcp_style != "config-file":
            mcp_config.unregister_cli_mcp(cli_cfg.cmd)
        if cwd is not None:
            shutil.rmtree(cwd, ignore_errors=True)


def run_cli_turn(*, messages: list[dict], config: CliTurnConfig, session_id: str,
                 prior_session_id: str | None, repository: AssistantRepository,
                 emit: Callable[[dict], None], spawn_fn=None) -> str:
    spawn_fn = spawn_fn or spawn_turn
    cli_cfg = load_cli_chat_config(config.provider)
    prompt = _latest_user(messages)
    if config.skill_block and cli_cfg.system_prompt_style == "message-prefix":
        # argv-append providers carry the skill inside --append-system-prompt;
        # message-prefix providers get it inline because normal turns send
        # only the latest user message.
        prompt = f"{config.skill_block}\n\n{prompt}"
    final, _sid, _rc = _run_once(
        config, cli_cfg, prompt=prompt, session_id=session_id,
        prior_session_id=prior_session_id, new_session_id=str(uuid.uuid4()),
        repository=repository, emit=emit, spawn_fn=spawn_fn)
    # replay only on a genuinely empty result; a non-empty answer is success
    # regardless of the exit code (some CLIs exit non-zero on benign warnings).
    if prior_session_id is not None and final == "":
        emit({"type": "warning", "message": "session rebuilt"})
        final, _sid, _rc = _run_once(
            config, cli_cfg, prompt=_full_transcript(messages), session_id=session_id,
            prior_session_id=None, new_session_id=str(uuid.uuid4()),
            repository=repository, emit=emit, spawn_fn=spawn_fn)
    if final == "":
        raise RuntimeError("CLI produced no output")
    return final
