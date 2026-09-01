"""AI CLI command-line construction and environment setup.

MCP/tool/model argument construction lives in _mcp_arg_builders.py;
_build_ai_cmd and the CLI MCP registration block stay here since their
patch targets (_get_provider_configs, get_ai_model, subprocess.run) are
resolved against this module.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

from quodeq.analysis._config import AnalysisConfig
from quodeq.analysis._mcp_arg_builders import (
    _build_base_args,
    _build_mcp_args,
    _build_model_budget_prompt_args,
    _cmd_binary,
    _get_ai_tools,  # noqa: F401 -- re-export
    _get_base_ai_args,  # noqa: F401 -- re-export
    _resolve_language,
    _resolve_model_id,
    _resolve_standards_dir,
)
from quodeq.analysis._provider_cache import get_provider_configs as _get_provider_configs
from quodeq.analysis.cache.local import default_cache_root as _default_cache_root
from quodeq.shared.utils import get_ai_cmd, get_ai_model

_log = logging.getLogger(__name__)


_SENSITIVE_ENV_KEYS = frozenset({
    "QUODEQ_API_KEY", "DATABASE_URL", "SECRET_KEY",
})


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
    standards_dir = _resolve_standards_dir(config)
    if standards_dir:
        mcp_args.extend(["--standards-dir", str(standards_dir.resolve())])
    if config.queue_path:
        mcp_args.extend(["--queue", str(config.queue_path.resolve())])
    if config.agent_id and not skip_agent_id:
        mcp_args.extend(["--agent-id", config.agent_id])
    wd = config.work_dir or work_dir
    if wd:
        mcp_args.extend(["--work-dir", str(wd.resolve())])
    # Phase 1.5 (Task 3.5): pass cache fingerprint inputs so findings_server
    # can write cache entries synchronously on each mark_file_done(ok). These
    # MUST match classify_files_via_cache's inputs so CLI- and API-path keys
    # agree for the same project state. See cache_writer.build_cache_writer
    # and cache.dimension_helpers._model_id_from for the reference.
    mcp_args.extend([
        "--cache-root", str(_default_cache_root()),
        "--model-id", _resolve_model_id(config),
        "--language", _resolve_language(config),
    ])
    return mcp_args


def _is_known_cli_provider(cmd: str) -> bool:
    """Return True only if *cmd* matches a registered provider of type 'cli'.

    ``cmd`` ultimately comes from the user-controlled AI_CMD/AI_PROVIDER env
    var (see ``quodeq.shared._env.get_ai_cmd``) with no prior validation. Gate
    subprocess execution to the known provider registry so a typo'd or
    unexpected value fails closed instead of shelling out to an arbitrary
    program. Only ``type == "cli"`` providers reach this CLI-register path;
    API-type providers (ollama, omlx, custom, ...) never do.
    """
    return _get_provider_configs().get(cmd, {}).get("type") == "cli"


def _register_cli_mcp(cmd: str, config: AnalysisConfig, work_dir: Path | None = None) -> str | None:
    """Register the findings MCP server via `<cmd> mcp add`.

    Thread-safe: only the first caller registers; subsequent calls return
    the cached name immediately.  Removes any stale registration first.
    Returns the server name on success, None on failure.
    """
    if not _is_known_cli_provider(cmd):
        _log.warning("Refusing to register MCP server: unknown CLI provider %r", cmd)
        return None
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
        register_cmd = [_cmd_binary(cmd), "mcp", "add", name]
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
    if not _is_known_cli_provider(cmd):
        return
    try:
        subprocess.run(
            [_cmd_binary(cmd), "mcp", "remove", name],
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
