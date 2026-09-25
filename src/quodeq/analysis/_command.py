"""AI CLI command-line construction and environment setup.

MCP/tool/model argument construction lives in _mcp_arg_builders.py;
build_ai_cmd and the CLI MCP registration block stay here since their
patch targets (_get_provider_configs, subprocess.run) are resolved against
this module. Nothing here reads the environment for provider selection:
``subprocess.run_analysis`` fills ``ai_cmd``/``ai_model``/``ai_cmd_path``/
``cache_root`` on the config before any of this runs.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path

from quodeq.analysis._config import AnalysisConfig
from quodeq.analysis._mcp_arg_builders import (
    build_base_args,
    build_mcp_args,
    build_model_budget_prompt_args,
    cmd_binary,
    get_ai_tools,  # noqa: F401 -- re-export
    get_base_ai_args,  # noqa: F401 -- re-export
    resolve_language,
    resolve_model_id,
    resolve_standards_dir,
)
from quodeq.analysis.provider_cache import get_provider_configs as _get_provider_configs
from quodeq.config.process_env import process_environment_copy
from quodeq.config.provider import Provider, ProviderType
from quodeq.shared.copilot import build_copilot_env
from quodeq.shared.log_sink import LoggerSink

_log = logging.getLogger(__name__)


_SENSITIVE_ENV_KEYS = frozenset({
    "QUODEQ_API_KEY", "DATABASE_URL", "SECRET_KEY",
})

_MCP_SUBPACKAGE = "mcp"  # this module's mcp/ subpackage, holding findings_server.py
_MCP_SUBCOMMAND = "mcp"  # the provider CLI's `<cmd> mcp add/remove` namespace


def build_ai_cmd(
    prompt: str, config: AnalysisConfig,
    work_dir: Path | None = None,
) -> tuple[list[str], Path | None]:
    """Build the AI CLI command line and optional MCP config path.

    *config* carries the resolved provider id, model and binary override
    (``run_analysis`` fills them); a direct caller sets them itself.
    """
    cmd = config.ai_cmd
    model = config.ai_model
    provider_cfg = _get_provider_configs().get(cmd, {})

    args = build_base_args(cmd, provider_cfg, ai_cmd_path=config.ai_cmd_path)
    mcp_args, mcp_config_path = build_mcp_args(
        config, provider_cfg, work_dir, log=LoggerSink(_log),
    )
    args.extend(mcp_args)
    if cmd == Provider.COPILOT and work_dir is not None:
        root = str(work_dir.resolve())
        args.extend(["--add-dir", root])
        prompt = (
            f"Repository root: {root}\nResolve relative source paths against this root.\n"
            "Use view, glob and grep where instructions refer to Read, Glob and Grep. "
            "Shell tools are unavailable.\n\n" + prompt
        )
    args.extend(build_model_budget_prompt_args(prompt, config, provider_cfg, model))

    return args, mcp_config_path


_MCP_REGISTER_TIMEOUT_S = 10
_MCP_SERVER_PREFIX = "quodeq-findings"


def _mcp_server_name() -> str:
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
    mcp_script = str(Path(__file__).resolve().parent / _MCP_SUBPACKAGE / "findings_server.py")
    mcp_args = [sys.executable, mcp_script, str(config.jsonl_file.resolve())]
    if config.compiled_dir and config.dimension:
        mcp_args.extend([
            "--compiled-dir", str(config.compiled_dir.resolve()),
            "--dimension", config.dimension,
        ])
    standards_dir = resolve_standards_dir(config)
    if standards_dir:
        mcp_args.extend(["--standards-dir", str(standards_dir.resolve())])
    if config.queue_path:
        mcp_args.extend(["--queue", str(config.queue_path.resolve())])
    if config.agent_id and not skip_agent_id:
        mcp_args.extend(["--agent-id", config.agent_id])
    wd = config.work_dir or work_dir
    if wd:
        mcp_args.extend(["--work-dir", str(wd.resolve())])
    # Pass cache fingerprint inputs so findings_server
    # can write cache entries synchronously on each mark_file_done(ok). These
    # MUST match classify_files_via_cache's inputs so CLI- and API-path keys
    # agree for the same project state. See cache_writer.build_cache_writer
    # and cache.dimension_helpers.model_id_from for the reference.
    if config.cache_root is not None:
        mcp_args.extend(["--cache-root", str(config.cache_root)])
    mcp_args.extend([
        "--model-id", resolve_model_id(config),
        "--language", resolve_language(config),
    ])
    return mcp_args


def _is_known_cli_provider(cmd: str) -> bool:
    """Return True only if *cmd* matches a registered provider of type 'cli'.

    ``cmd`` ultimately comes from the user-controlled AI_CMD/AI_PROVIDER env
    var (see ``quodeq.shared.env.get_ai_cmd``) with no prior validation. Gate
    subprocess execution to the known provider registry so a typo'd or
    unexpected value fails closed instead of shelling out to an arbitrary
    program. Only ``type == "cli"`` providers reach this CLI-register path;
    API-type providers (ollama, omlx, custom, ...) never do.
    """
    return _get_provider_configs().get(cmd, {}).get("type") == ProviderType.CLI


class CliMcpRegistry:
    """CLI-register MCP server names registered so far, for one scope.

    Wraps the same lock-guarded set the old module globals held. Production
    keys one instance per run (``RunConfig.mcp_registry``), shared by every
    pool worker thread of that run via ``dataclasses.replace()`` copies, so
    the first agent registers and the rest see the cached name. Tests (or
    any caller with no run scope) get :data:`DEFAULT_CLI_MCP_REGISTRY`.
    """

    def __init__(self) -> None:
        self._cli_mcp_lock = threading.Lock()
        self._cli_mcp_registered: set[str] = set()  # tracks (cmd, name) pairs

    def ensure_registered(
        self, cmd: str, config: AnalysisConfig, work_dir: Path | None = None,
    ) -> str | None:
        """Register the findings MCP server via `<cmd> mcp add`.

        Thread-safe: only the first caller registers; subsequent calls return
        the cached name immediately.  Removes any stale registration first.
        Returns the server name on success, None on failure.
        """
        if not _is_known_cli_provider(cmd):
            _log.warning("Refusing to register MCP server: unknown CLI provider %r", cmd)
            return None
        name = _mcp_server_name()
        key = f"{cmd}:{name}"
        with self._cli_mcp_lock:
            if key in self._cli_mcp_registered:
                return name
            _unregister_cli_mcp(cmd, name, config.ai_cmd_path)
            # Skip agent-id: all agents share one MCP server, so per-agent
            # file caps don't apply — the queue distributes freely.
            mcp_args = _build_mcp_server_args(config, work_dir, skip_agent_id=True)
            provider_cfg = _get_provider_configs().get(cmd, {})
            # Codex/Copilot use "-- cmd args", Gemini uses "cmd args" (no separator)
            use_separator = provider_cfg.get("mcp_add_separator", True)
            register_cmd = [cmd_binary(cmd, config.ai_cmd_path), _MCP_SUBCOMMAND, "add", name]
            if use_separator:
                register_cmd.append("--")
            register_cmd.extend(mcp_args)
            _log.debug("Registering MCP server '%s': %s", name, " ".join(register_cmd))
            try:
                subprocess.run(register_cmd, check=True, capture_output=True, timeout=_MCP_REGISTER_TIMEOUT_S)
                self._cli_mcp_registered.add(key)
                return name
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
                _log.warning("Failed to register MCP server '%s' via '%s mcp add': %s", name, cmd, exc)
                return None

    def clear(self) -> None:
        """Drop every cached registration (test isolation)."""
        with self._cli_mcp_lock:
            self._cli_mcp_registered.clear()

    def __contains__(self, key: str) -> bool:
        with self._cli_mcp_lock:
            return key in self._cli_mcp_registered


# Process-wide fallback for callers with no run-scoped registry (tests,
# one-shot callers). Production runs get a fresh, isolated instance via
# ``RunConfig.mcp_registry`` instead.
DEFAULT_CLI_MCP_REGISTRY = CliMcpRegistry()


def register_cli_mcp(cmd: str, config: AnalysisConfig, work_dir: Path | None = None) -> str | None:
    """Register the findings MCP server on the process-default registry.

    Back-compat entry point for callers with no run scope; a run-scoped
    caller uses ``config.run_config.mcp_registry.ensure_registered(...)``
    directly (see ``subprocess._run_cli_analysis``).
    """
    return DEFAULT_CLI_MCP_REGISTRY.ensure_registered(cmd, config, work_dir)


def _unregister_cli_mcp(cmd: str, name: str, ai_cmd_path: str | None = None) -> None:
    """Remove the findings MCP server via `<cmd> mcp remove`."""
    if not _is_known_cli_provider(cmd):
        return
    try:
        subprocess.run(
            [cmd_binary(cmd, ai_cmd_path), _MCP_SUBCOMMAND, "remove", name],
            check=False, capture_output=True, timeout=_MCP_REGISTER_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        _log.warning("Failed to unregister MCP server '%s' via '%s mcp remove': %s", name, cmd, exc)


def build_analysis_env(ai_cmd: str | None = None, env: dict[str, str] | None = None) -> dict[str, str]:
    """Build the subprocess environment, removing sensitive variables.

    The ``None`` default resolves to the process environment in the config
    layer; an injected ``{}`` means "no variables set".
    """
    env = process_environment_copy(env)
    for key in _SENSITIVE_ENV_KEYS:
        env.pop(key, None)
    provider_cfg = _get_provider_configs().get(ai_cmd or "", {})
    for key, val in provider_cfg.get("env_set_if_missing", {}).items():
        if key not in env:
            env[key] = val
    for key in provider_cfg.get("env_remove", []):
        env.pop(key, None)
    if ai_cmd == Provider.COPILOT:
        return build_copilot_env(env)
    return env
