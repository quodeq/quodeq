"""AI CLI command-line construction and environment setup."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
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

_log = logging.getLogger(__name__)

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


def _build_base_args(cmd: str, provider_cfg: dict) -> list[str]:
    """Build the initial args list: binary, subcommand, base args, and tools."""
    args: list[str] = [cmd]
    subcommand = provider_cfg.get("cmd_subcommand", "")
    if subcommand:
        args.append(subcommand)

    base_args_str = provider_cfg.get("base_args", "")
    if base_args_str:
        args.extend(base_args_str.split())
    else:
        args.extend(_get_base_ai_args())

    if provider_cfg.get("supports_tools", True):
        args.extend(["--tools", _get_ai_tools()])
    return args


def _build_mcp_args(
    config: AnalysisConfig, provider_cfg: dict, work_dir: Path | None,
) -> tuple[list[str], Path | None]:
    """Build MCP-related args and return the config path (if any)."""
    if config.jsonl_file is None:
        return [], None
    mcp_style = provider_cfg.get("mcp_style", "config-file")
    if mcp_style != "config-file":
        return [], None

    agent_params = _AgentParams(
        queue_path=config.queue_path,
        agent_id=config.agent_id,
        work_dir=config.work_dir or work_dir,
    )
    mcp_config_path = _create_mcp_config(
        config.jsonl_file, config.compiled_dir, config.dimension, agent_params,
    )
    mcp_flag = provider_cfg.get("mcp_config_flag", "--mcp-config")
    mcp_prefix = provider_cfg.get("mcp_config_prefix", "")
    args: list[str] = [mcp_flag, f"{mcp_prefix}{mcp_config_path}"]

    if provider_cfg.get("supports_tools", True):
        allowed = _MCP_TOOL_REPORT_FINDING
        if config.queue_path:
            allowed += f",{_MCP_TOOL_GET_NEXT_FILES}"
        args.extend(["--allowedTools", allowed])
    # bypassPermissions is intentional: the CLI analysis tool runs in a
    # sandboxed, non-interactive subprocess where MCP tool calls (e.g.
    # report_finding) must succeed without user confirmation prompts.
    # The subprocess has no access to credentials or network beyond
    # what the parent process explicitly provides via env filtering.
    args.extend(
        provider_cfg.get("mcp_permission_args", ["--permission-mode", "bypassPermissions"])
    )
    return args, mcp_config_path


def _build_model_budget_prompt_args(
    prompt: str, config: AnalysisConfig, provider_cfg: dict, model: str,
) -> list[str]:
    """Build model, budget, turns, and prompt args."""
    args: list[str] = []
    if model:
        args.extend(["--model", model])
    if provider_cfg.get("supports_budget", True) and config.analysis_budget:
        args.extend(["--max-budget-usd", str(config.analysis_budget)])
    if provider_cfg.get("supports_turns", True) and config.max_turns is not None:
        args.extend(["--max-turns", str(config.max_turns)])

    prompt_style = provider_cfg.get("prompt_style", "flag")
    if prompt_style == "positional":
        args.append(prompt)
    else:
        prompt_flag = provider_cfg.get("prompt_flag", "-p")
        args.extend([prompt_flag, prompt])
    return args


def _build_ai_cmd(
    prompt: str, config: AnalysisConfig,
    work_dir: Path | None = None,
) -> tuple[list[str], Path | None]:
    """Build the AI CLI command line and optional MCP config path."""
    cmd = config.ai_cmd or get_ai_cmd()
    model = config.ai_model or get_ai_model()
    provider_cfg = _get_provider_configs().get(cmd, {})

    args = _build_base_args(cmd, provider_cfg)
    mcp_args, mcp_config_path = _build_mcp_args(config, provider_cfg, work_dir)
    args.extend(mcp_args)
    args.extend(_build_model_budget_prompt_args(prompt, config, provider_cfg, model))

    return args, mcp_config_path


_MCP_REGISTER_TIMEOUT_S = 10
_MCP_SERVER_PREFIX = "quodeq-findings"
_cli_mcp_lock = threading.Lock()
_cli_mcp_registered: set[str] = set()  # tracks (cmd, name) pairs


def _reset_mcp_registry() -> None:
    """Clear the MCP registration cache. Useful for test isolation."""
    with _cli_mcp_lock:
        _cli_mcp_registered.clear()


def _mcp_server_name(config: AnalysisConfig) -> str:
    """Return the MCP server name.

    All agents share one global server so that each ``codex exec`` process
    sees exactly one ``report_finding`` / ``get_next_files`` tool.
    """
    return _MCP_SERVER_PREFIX


def _build_mcp_server_args(
    config: AnalysisConfig,
    work_dir: Path | None = None,
    skip_agent_id: bool = False,
) -> list[str]:
    """Build the MCP findings server command-line args.

    *skip_agent_id*: set True for cli-register MCP where all agents share
    one server — the per-agent file cap doesn't apply.
    """
    mcp_script = str(Path(__file__).resolve().parent / "mcp" / "findings_server.py")
    mcp_args = [sys.executable, mcp_script, str(config.jsonl_file.resolve())]
    if config.compiled_dir and config.dimension:
        mcp_args.extend([
            "--compiled-dir", str(config.compiled_dir.resolve()),
            "--dimension", config.dimension,
        ])
    if config.queue_path:
        mcp_args.extend(["--queue", str(config.queue_path.resolve())])
    if config.agent_id and not skip_agent_id:
        mcp_args.extend(["--agent-id", config.agent_id])
    wd = config.work_dir or work_dir
    if wd:
        mcp_args.extend(["--work-dir", str(wd.resolve())])
    return mcp_args


def _register_cli_mcp(cmd: str, config: AnalysisConfig, work_dir: Path | None = None) -> str | None:
    """Register the findings MCP server via `<cmd> mcp add`.

    Thread-safe: only the first caller registers; subsequent calls return
    the cached name immediately.  Removes any stale registration first.
    Returns the server name on success, None on failure.
    """
    name = _mcp_server_name(config)
    key = f"{cmd}:{name}"
    with _cli_mcp_lock:
        if key in _cli_mcp_registered:
            return name
        _unregister_cli_mcp(cmd, name)
        # Skip agent-id: all agents share one MCP server, so per-agent
        # file caps don't apply — the queue distributes freely.
        mcp_args = _build_mcp_server_args(config, work_dir, skip_agent_id=True)
        provider_cfg = _get_provider_configs().get(cmd, {})
        # Codex/Copilot use "-- cmd args", Gemini uses "cmd args" (no separator)
        use_separator = provider_cfg.get("mcp_add_separator", True)
        register_cmd = [cmd, "mcp", "add", name]
        if use_separator:
            register_cmd.append("--")
        register_cmd.extend(mcp_args)
        _log.debug("Registering MCP server '%s': %s", name, " ".join(register_cmd))
        try:
            subprocess.run(register_cmd, check=True, capture_output=True, timeout=_MCP_REGISTER_TIMEOUT_S)
            _cli_mcp_registered.add(key)
            return name
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            _log.warning("Failed to register MCP server '%s' via '%s mcp add': %s", name, cmd, exc)
            return None


def _unregister_cli_mcp(cmd: str, name: str) -> None:
    """Remove the findings MCP server via `<cmd> mcp remove`."""
    try:
        subprocess.run(
            [cmd, "mcp", "remove", name],
            check=False, capture_output=True, timeout=_MCP_REGISTER_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


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
