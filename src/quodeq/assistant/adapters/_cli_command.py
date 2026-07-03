"""Build the argv for one CLI chat turn (hardened, with session resume)."""
from __future__ import annotations

from dataclasses import dataclass

from quodeq.assistant.adapters._cli_config import CliChatConfig


@dataclass(frozen=True)
class CliTurnSpec:
    argv: list[str]
    session_id: str | None
    needs_id_parse: bool


def _resume_args(cfg: CliChatConfig, prior: str | None, new_id: str) -> tuple[list[str], str | None, bool]:
    """Return (session-related argv fragment, assigned id, needs_parse)."""
    if cfg.session_id_source == "parse-jsonl":
        # codex: turn 1 plain exec (parse id); turn N `resume <id>` after subcommand
        if prior is None:
            return [], None, True
        return ["resume", prior], None, False
    # preassign providers (claude, gemini)
    if prior is None:
        return ["--session-id", new_id], new_id, False
    if cfg.resume_style == "gemini-resume":
        return ["-r", prior], prior, False
    return ["--resume", prior], prior, False


def build_turn_argv(cfg: CliChatConfig, *, prompt: str, model: str | None,
                    mcp_config_path: str | None, prior_session_id: str | None,
                    new_session_id: str) -> CliTurnSpec:
    argv: list[str] = [cfg.cmd]
    if cfg.cmd_subcommand:
        argv.append(cfg.cmd_subcommand)

    resume_frag, assigned, needs_parse = _resume_args(cfg, prior_session_id, new_session_id)
    # codex `resume <id>` must sit immediately after the `exec` subcommand
    if cfg.session_id_source == "parse-jsonl" and resume_frag:
        argv.extend(resume_frag)
        resume_frag = []

    argv.extend(cfg.assistant_args)
    if resume_frag:
        argv.extend(resume_frag)
    if mcp_config_path and cfg.mcp_style == "config-file":
        argv.extend(["--mcp-config", mcp_config_path])
    if model:
        argv.extend(["--model", model])

    if cfg.prompt_style == "positional":
        argv.append(prompt)
    else:
        argv.extend([cfg.prompt_flag, prompt])
    return CliTurnSpec(argv=argv, session_id=assigned, needs_id_parse=needs_parse)
