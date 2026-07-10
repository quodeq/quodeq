"""Build the argv for one CLI chat turn (hardened, with session resume)."""
from __future__ import annotations

from dataclasses import dataclass

from quodeq.assistant.adapters._cli_config import CliChatConfig
from quodeq.shared._models import normalize_model_id

_NATIVE_WEB_TOOLS = ("WebSearch", "WebFetch")


def _with_web_access(args: list[str]) -> list[str]:
    """Enable the provider's native web tools in an assistant_args list.

    Claude encodes tool names as ONE space-separated value token after
    --disallowedTools / --allowedTools. Providers without those flags
    (codex, gemini) come back unchanged, so a web-enabled turn is inert
    for them.
    """
    out = list(args)
    # The value token following each flag comes only from the static bundled
    # config (ai_providers.json), so degenerate/empty values need no handling.
    for i, token in enumerate(out[:-1]):
        if token == "--disallowedTools":
            names = [n for n in out[i + 1].split() if n not in _NATIVE_WEB_TOOLS]
            out[i + 1] = " ".join(names)
        elif token == "--allowedTools":
            names = out[i + 1].split()
            out[i + 1] = " ".join(names + [n for n in _NATIVE_WEB_TOOLS if n not in names])
    return out


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


def _model_arg(cfg: CliChatConfig, model: str | None) -> str | None:
    if not model:
        return None
    return normalize_model_id(cfg.cmd, model)


def build_turn_argv(cfg: CliChatConfig, *, prompt: str, model: str | None,
                    mcp_config_path: str | None, prior_session_id: str | None,
                    new_session_id: str, web_enabled: bool = False,
                    system_prompt: str = "", mcp_config_arg: str | None = None) -> CliTurnSpec:
    argv: list[str] = [cfg.cmd]
    if cfg.cmd_subcommand:
        argv.append(cfg.cmd_subcommand)

    resume_frag, assigned, needs_parse = _resume_args(cfg, prior_session_id, new_session_id)
    # codex `resume <id>` must sit immediately after the `exec` subcommand
    if cfg.session_id_source == "parse-jsonl" and resume_frag:
        argv.extend(resume_frag)
        resume_frag = []

    argv.extend(_with_web_access(cfg.assistant_args) if web_enabled else cfg.assistant_args)
    if resume_frag:
        argv.extend(resume_frag)
    if mcp_config_path and cfg.mcp_style == "config-file":
        argv.extend(["--mcp-config", mcp_config_path])
    if mcp_config_arg and cfg.mcp_style == "config-arg":
        argv.extend(["-c", mcp_config_arg])
    normalized_model = _model_arg(cfg, model)
    if normalized_model:
        argv.extend(["--model", normalized_model])
    if system_prompt and cfg.system_prompt_style == "argv-append":
        argv.extend(["--append-system-prompt", system_prompt])

    if cfg.prompt_style == "positional":
        argv.append(prompt)
    else:
        argv.extend([cfg.prompt_flag, prompt])
    return CliTurnSpec(argv=argv, session_id=assigned, needs_id_parse=needs_parse)
