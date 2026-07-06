"""Per-provider CLI chat configuration (assistant_args, resume style, session-id source)."""
from __future__ import annotations

from dataclasses import dataclass

from quodeq.assistant import get_provider_configs


@dataclass(frozen=True)
class CliChatConfig:
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


def load_cli_chat_config(provider_id: str) -> CliChatConfig:
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
        prompt_style=cfg.get("prompt_style", "flag"),
        prompt_flag=cfg.get("prompt_flag", "-p"),
        mcp_style=cfg.get("mcp_style", "config-file"),
        mcp_add_separator=cfg.get("mcp_add_separator", True),
        resume_style=assistant.get("resume_style", "flag-resume"),
        session_id_source=assistant.get("session_id_source", "preassign"),
        supports_tools=cfg.get("supports_tools", True),
        system_prompt_style=assistant.get("system_prompt_style", "message-prefix"),
        requires_external_sandbox=cfg.get("requires_external_sandbox", False),
    )
