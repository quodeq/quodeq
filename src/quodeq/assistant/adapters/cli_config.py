"""Per-provider CLI chat configuration (assistant_args, resume style, session-id source)."""
from __future__ import annotations

from dataclasses import dataclass

from quodeq.assistant import get_provider_configs
from quodeq.core.constants import MCP_STYLE_CONFIG_FILE, PROMPT_FLAG_DEFAULT, PROMPT_STYLE_FLAG

# Per-provider discriminators for the assistant-only CliChatConfig fields
# (resume_style, session_id_source, system_prompt_style), sourced from the
# ai_providers.json "assistant" block. _cli.py and _cli_command.py, the two
# consumers, import these rather than retyping the strings.
RESUME_STYLE_FLAG_RESUME = "flag-resume"  # --resume <id> (claude, copilot); the default when unset
RESUME_STYLE_EXEC = "exec-resume"  # `exec resume <id>` after the subcommand (codex)
RESUME_STYLE_GEMINI = "gemini-resume"  # -r <id>
SESSION_ID_SOURCE_PREASSIGN = "preassign"  # --session-id <new-id> on turn 1
SESSION_ID_SOURCE_PARSE_JSONL = "parse-jsonl"  # id parsed from the stream (codex)
SYSTEM_PROMPT_STYLE_MESSAGE_PREFIX = "message-prefix"  # prepended to the first user message
SYSTEM_PROMPT_STYLE_ARGV_APPEND = "argv-append"  # passed via --append-system-prompt

MCP_CONFIG_FLAG_DEFAULT = "--mcp-config"
MCP_CONFIG_PREFIX_DEFAULT = ""


@dataclass(frozen=True)
class CliChatConfig:
    """One provider's CLI chat contract, as read from the provider catalog."""

    cmd: str
    cmd_subcommand: str
    base_args: list[str]
    assistant_args: list[str]
    prompt_style: str
    prompt_flag: str
    mcp_style: str
    mcp_add_separator: bool
    resume_style: str
    session_id_source: str
    supports_tools: bool
    system_prompt_style: str
    requires_external_sandbox: bool
    mcp_config_flag: str = MCP_CONFIG_FLAG_DEFAULT
    mcp_config_prefix: str = MCP_CONFIG_PREFIX_DEFAULT
    mcp_server_tools: tuple[str, ...] | None = None


def load_cli_chat_config(provider_id: str) -> CliChatConfig:
    """Return ``provider_id``'s CLI chat config; raise KeyError if unknown."""
    catalog = get_provider_configs()
    if provider_id not in catalog:
        raise KeyError(f"unknown provider: {provider_id}")
    cfg = catalog[provider_id]
    assistant = cfg.get("assistant", {})
    return CliChatConfig(
        cmd=cfg.get("cmd", provider_id),
        cmd_subcommand=cfg.get("cmd_subcommand", ""),
        base_args=(cfg.get("base_args", "") or "").split(),
        assistant_args=list(assistant.get("assistant_args", [])),
        prompt_style=cfg.get("prompt_style", PROMPT_STYLE_FLAG),
        prompt_flag=cfg.get("prompt_flag", PROMPT_FLAG_DEFAULT),
        mcp_style=cfg.get("mcp_style", MCP_STYLE_CONFIG_FILE),
        mcp_add_separator=cfg.get("mcp_add_separator", True),
        resume_style=assistant.get("resume_style", RESUME_STYLE_FLAG_RESUME),
        session_id_source=assistant.get("session_id_source", SESSION_ID_SOURCE_PREASSIGN),
        supports_tools=cfg.get("supports_tools", True),
        system_prompt_style=assistant.get("system_prompt_style", SYSTEM_PROMPT_STYLE_MESSAGE_PREFIX),
        requires_external_sandbox=cfg.get("requires_external_sandbox", False),
        mcp_config_flag=cfg.get("mcp_config_flag", MCP_CONFIG_FLAG_DEFAULT),
        mcp_config_prefix=cfg.get("mcp_config_prefix", MCP_CONFIG_PREFIX_DEFAULT),
        mcp_server_tools=tuple(cfg["mcp_server_tools"]) if "mcp_server_tools" in cfg else None,
    )
