"""AI CLI command-line construction and environment setup."""
from __future__ import annotations

import os
from pathlib import Path

from quodeq.analysis._config import (
    AnalysisConfig,
    _AgentParams,
    _MCP_TOOL_GET_NEXT_FILES,
    _MCP_TOOL_REPORT_FINDING,
)
from quodeq.analysis._mcp_config import _create_mcp_config
from quodeq.analysis._provider_cache import get_provider_configs as _get_provider_configs
from quodeq.shared.utils import get_ai_cmd, get_ai_model

_DEFAULT_AI_TOOLS = "Glob,Grep,Read"
_DEFAULT_BASE_AI_ARGS = "--print --output-format stream-json --verbose"

_SENSITIVE_ENV_KEYS = frozenset({
    "QUODEQ_API_KEY", "DATABASE_URL", "SECRET_KEY",
})


def _get_ai_tools(env: dict[str, str] | None = None) -> str:
    """Return AI tools from QUODEQ_AI_TOOLS env var (default: "Glob,Grep,Read")."""
    return (env or os.environ).get("QUODEQ_AI_TOOLS", _DEFAULT_AI_TOOLS)


def _get_base_ai_args(env: dict[str, str] | None = None) -> tuple[str, ...]:
    """Return base AI CLI args from QUODEQ_AI_BASE_ARGS env var."""
    return tuple((env or os.environ).get("QUODEQ_AI_BASE_ARGS", _DEFAULT_BASE_AI_ARGS).split())


def _build_ai_cmd(
    prompt: str, config: AnalysisConfig,
    work_dir: Path | None = None,
) -> tuple[list[str], Path | None]:
    """Build the AI CLI command line and optional MCP config path."""
    cmd = config.ai_cmd or get_ai_cmd()
    model = config.ai_model or get_ai_model()

    args = [cmd, *_get_base_ai_args(), "--tools", _get_ai_tools()]

    provider_cfg = _get_provider_configs().get(cmd, {})
    mcp_config_path: Path | None = None
    if config.jsonl_file is not None:
        mcp_config_path = _create_mcp_config(
            config.jsonl_file, config.compiled_dir, config.dimension,
            _AgentParams(queue_path=config.queue_path, agent_id=config.agent_id, work_dir=config.work_dir or work_dir),
        )
        args.extend(["--mcp-config", str(mcp_config_path)])
        allowed = _MCP_TOOL_REPORT_FINDING
        if config.queue_path:
            allowed += f",{_MCP_TOOL_GET_NEXT_FILES}"
        args.extend(["--allowedTools", allowed])
        args.extend(provider_cfg.get("mcp_permission_args", ["--permission-mode", "bypassPermissions"]))

    if model:
        args.extend(["--model", model])
    if config.analysis_budget:
        args.extend(["--max-budget-usd", str(config.analysis_budget)])
    if config.max_turns is not None:
        args.extend(["--max-turns", str(config.max_turns)])
    args.extend(["-p", prompt])

    return args, mcp_config_path


def _build_analysis_env(ai_cmd: str | None = None, env: dict[str, str] | None = None) -> dict[str, str]:
    """Build the subprocess environment, removing sensitive variables."""
    env = (env or os.environ).copy()
    for key in _SENSITIVE_ENV_KEYS:
        env.pop(key, None)
    provider_cfg = _get_provider_configs().get(ai_cmd or "", {})
    for key, val in provider_cfg.get("env_set_if_missing", {}).items():
        if key not in env:
            env[key] = val
    for key in provider_cfg.get("env_remove", []):
        env.pop(key, None)
    return env
