"""quodeq.core._constants' MCP/prompt style constants agree across their
producer (ai_providers.json, consumed via quodeq.analysis._provider_cache /
quodeq.assistant.get_provider_configs) and its two feature consumers:
quodeq.analysis (dimension-analysis subprocess dispatch) and
quodeq.assistant.adapters (interactive CLI chat). Both features import the
same constants rather than retyping the "config-file" / "config-arg" /
"cli-register" / "flag" / "positional" / "-p" strings, so a rename here can't
silently desync one side's comparison from the other's.
"""
from __future__ import annotations

from quodeq.core._constants import (
    MCP_STYLE_CLI_REGISTER, MCP_STYLE_CONFIG_ARG, MCP_STYLE_CONFIG_FILE,
    PROMPT_FLAG_DEFAULT, PROMPT_STYLE_FLAG, PROMPT_STYLE_POSITIONAL,
)


def test_analysis_mcp_arg_builders_uses_the_shared_constants():
    from quodeq.analysis import _mcp_arg_builders

    assert _mcp_arg_builders.MCP_STYLE_CONFIG_FILE is MCP_STYLE_CONFIG_FILE
    assert _mcp_arg_builders.MCP_STYLE_CONFIG_ARG is MCP_STYLE_CONFIG_ARG
    assert _mcp_arg_builders.MCP_STYLE_CLI_REGISTER is MCP_STYLE_CLI_REGISTER
    assert _mcp_arg_builders.PROMPT_STYLE_FLAG is PROMPT_STYLE_FLAG
    assert _mcp_arg_builders.PROMPT_STYLE_POSITIONAL is PROMPT_STYLE_POSITIONAL
    assert _mcp_arg_builders.PROMPT_FLAG_DEFAULT is PROMPT_FLAG_DEFAULT


def test_analysis_subprocess_uses_the_shared_mcp_style_constants():
    from quodeq.analysis import subprocess as analysis_subprocess

    assert analysis_subprocess.MCP_STYLE_CONFIG_FILE is MCP_STYLE_CONFIG_FILE
    assert analysis_subprocess.MCP_STYLE_CLI_REGISTER is MCP_STYLE_CLI_REGISTER


def test_assistant_cli_config_uses_the_shared_constants():
    from quodeq.assistant.adapters import _cli_config

    assert _cli_config.MCP_STYLE_CONFIG_FILE is MCP_STYLE_CONFIG_FILE
    assert _cli_config.PROMPT_STYLE_FLAG is PROMPT_STYLE_FLAG
    assert _cli_config.PROMPT_FLAG_DEFAULT is PROMPT_FLAG_DEFAULT


def test_assistant_cli_command_uses_the_shared_constants():
    from quodeq.assistant.adapters import _cli_command

    assert _cli_command.MCP_STYLE_CONFIG_FILE is MCP_STYLE_CONFIG_FILE
    assert _cli_command.MCP_STYLE_CONFIG_ARG is MCP_STYLE_CONFIG_ARG
    assert _cli_command.PROMPT_STYLE_POSITIONAL is PROMPT_STYLE_POSITIONAL


def test_assistant_cli_cleanup_uses_the_shared_mcp_style_constant():
    from quodeq.assistant.adapters import _cli_cleanup

    assert _cli_cleanup.MCP_STYLE_CLI_REGISTER is MCP_STYLE_CLI_REGISTER


def test_assistant_orchestrator_isolated_styles_match_the_shared_constants():
    from quodeq.assistant.orchestrator import _ISOLATED_MCP_STYLES

    assert _ISOLATED_MCP_STYLES == {MCP_STYLE_CONFIG_FILE, MCP_STYLE_CONFIG_ARG}
