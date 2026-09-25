"""MCP/tool/model command-line argument construction for the AI CLI runner.

Split out of _command.py: env-driven tool/base-arg defaults, the base-args
and MCP-config args builders (config-file / config-arg / cli-register
dispatch), the model/budget/turns/prompt args builder, and the RunConfig
cache-fingerprint resolvers those builders (and _command.py's own
``_build_mcp_server_args``) share. None of these names are mock.patch
targets -- ``build_ai_cmd`` (in _command.py) receives ``provider_cfg``
already resolved and passes it straight through.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from quodeq.analysis._config import (
    AnalysisConfig,
    AgentParams,
    MCP_TOOL_GET_NEXT_FILES,
    MCP_TOOL_MARK_FILE_DONE,
    MCP_TOOL_REPORT_FINDING,
)
from quodeq.analysis._mcp_config import codex_mcp_config_arg, create_mcp_config
from quodeq.config.analysis_env import ai_tools, base_ai_args
from quodeq.core.constants import (
    MCP_CONFIG_ARG_FLAG, MCP_STYLE_CLI_REGISTER, MCP_STYLE_CONFIG_ARG, MCP_STYLE_CONFIG_FILE,
    PROMPT_FLAG_DEFAULT, PROMPT_STYLE_FLAG, PROMPT_STYLE_POSITIONAL,
)
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.shared.models import normalize_model_id
from quodeq.shared.utils import get_ai_cmd_path


def get_ai_tools(env: Mapping[str, str] | None = None) -> str:
    """Return AI tools from QUODEQ_AI_TOOLS env var (default: "Glob,Grep,Read")."""
    return ai_tools(env)


def get_base_ai_args(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Return base AI CLI args from QUODEQ_AI_BASE_ARGS env var."""
    return tuple(base_ai_args(env).split())


def cmd_binary(cmd: str) -> str:
    """Return the binary to spawn for provider *cmd*.

    AI_CMD_PATH (validated at the API boundary, see
    api._evaluation_helpers.validate_ai_cmd_path) redirects the spawn to an
    alternate install or wrapper while *cmd* keeps keying the provider config.
    """
    return get_ai_cmd_path() or cmd


def build_base_args(
    cmd: str, provider_cfg: dict, env: Mapping[str, str] | None = None,
) -> list[str]:
    """Build the initial args list: binary, subcommand, base args, and tools."""
    args: list[str] = [cmd_binary(cmd)]
    subcommand = provider_cfg.get("cmd_subcommand", "")
    if subcommand:
        args.append(subcommand)

    base_args_str = provider_cfg.get("base_args", "")
    if base_args_str:
        args.extend(base_args_str.split())
    else:
        args.extend(get_base_ai_args(env))

    if provider_cfg.get("supports_tools", True):
        args.extend(["--tools", get_ai_tools(env)])
    return args


def _build_agent_params(config: AnalysisConfig, work_dir: Path | None) -> AgentParams:
    """Build the per-agent MCP config parameters, incl. cache fingerprint inputs."""
    return AgentParams(
        queue_path=config.queue_path,
        agent_id=config.agent_id,
        work_dir=config.work_dir or work_dir,
        # The cache fingerprint inputs travel the config-file path too:
        # without them the JSON-config MCP variant emits defaults and its
        # cache writes diverge from the classify_files_via_cache keys.
        model_id=resolve_model_id(config),
        language=resolve_language(config),
        # The standards ROOT, not compiled_dir -- see resolve_standards_dir
        # and AgentParams.standards_dir.
        standards_dir=resolve_standards_dir(config),
    )


def _build_config_file_mcp_args(
    config: AnalysisConfig, provider_cfg: dict, agent_params: AgentParams,
) -> tuple[list[str], Path | None]:
    """Build the config-file MCP variant's args: --mcp-config, strict-mode,
    allowed tools, and permission mode."""
    options = {"tools": provider_cfg["mcp_server_tools"]} if "mcp_server_tools" in provider_cfg else {}
    mcp_config_path = create_mcp_config(
        config.jsonl_file, config.compiled_dir, config.dimension, agent_params, **options,
    )
    mcp_flag = provider_cfg.get("mcp_config_flag", "--mcp-config")
    mcp_prefix = provider_cfg.get("mcp_config_prefix", "")
    args: list[str] = [mcp_flag, f"{mcp_prefix}{mcp_config_path}"]
    # Restrict the subprocess to the findings server only. Without this the
    # CLI also loads the user's own MCP servers (user/project scope), and
    # bypassPermissions would let the model call them.
    args.extend(provider_cfg.get("mcp_strict_args", ["--strict-mcp-config"]))

    if provider_cfg.get("supports_tools", True):
        allowed = MCP_TOOL_REPORT_FINDING
        if config.queue_path:
            allowed += f",{MCP_TOOL_GET_NEXT_FILES}"
        # mark_file_done is always exposed by the findings server (see
        # handlers.handle_tools_list) and drives cache writes, so allow it
        # unconditionally rather than leaving it to bypassPermissions.
        allowed += f",{MCP_TOOL_MARK_FILE_DONE}"
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


def build_mcp_args(
    config: AnalysisConfig, provider_cfg: dict, work_dir: Path | None,
    *, log: LogSink = NULL_LOG,
) -> tuple[list[str], Path | None]:
    """Build MCP-related args and return the config path (if any)."""
    if config.jsonl_file is None:
        return [], None
    mcp_style = provider_cfg.get("mcp_style", MCP_STYLE_CONFIG_FILE)
    if mcp_style == MCP_STYLE_CLI_REGISTER:
        # The findings server is registered out-of-band (`<cmd> mcp add` in
        # subprocess._run_cli_analysis), so no config file/arg is needed —
        # but the CLI must still receive its allow-list args (e.g. gemini's
        # --allowed-mcp-server-names) or the registered server stays blocked.
        return list(provider_cfg.get("mcp_permission_args", [])), None
    if mcp_style not in {MCP_STYLE_CONFIG_FILE, MCP_STYLE_CONFIG_ARG}:
        log.warning(
            f"unknown mcp_style {mcp_style!r} for provider {config.ai_cmd or 'unknown'}; "
            "no MCP args emitted"
        )
        return [], None

    agent_params = _build_agent_params(config, work_dir)
    if mcp_style == MCP_STYLE_CONFIG_ARG:
        return [
            MCP_CONFIG_ARG_FLAG,
            codex_mcp_config_arg(
                config.jsonl_file, config.compiled_dir, config.dimension, agent_params,
            ),
        ], None

    return _build_config_file_mcp_args(config, provider_cfg, agent_params)


def build_model_budget_prompt_args(
    prompt: str, config: AnalysisConfig, provider_cfg: dict, model: str,
) -> list[str]:
    """Build model, budget, turns, and prompt args."""
    args: list[str] = []
    if model:
        args.extend(["--model", normalize_model_id(provider_cfg.get("cmd", ""), model)])
    if provider_cfg.get("supports_budget", True) and config.analysis_budget:
        args.extend(["--max-budget-usd", str(config.analysis_budget)])
    if provider_cfg.get("supports_turns", True) and config.max_turns is not None:
        args.extend(["--max-turns", str(config.max_turns)])

    prompt_style = provider_cfg.get("prompt_style", PROMPT_STYLE_FLAG)
    if prompt_style == PROMPT_STYLE_POSITIONAL:
        args.append(prompt)
    else:
        prompt_flag = provider_cfg.get("prompt_flag", PROMPT_FLAG_DEFAULT)
        args.extend([prompt_flag, prompt])
    return args


def resolve_model_id(config: AnalysisConfig) -> str:
    """Pick the most specific model identifier available for cache keys.

    Mirrors ``cache.dimension_helpers.model_id_from`` when a RunConfig is
    carried; otherwise falls back to ``AnalysisConfig.ai_model``; otherwise
    ``"unknown"``.
    """
    rc = config.run_config
    if rc is not None:
        opts = getattr(rc, "options", None)
        if opts is not None:
            return (
                getattr(opts, "subagent_model", None)
                or getattr(opts, "ai_model", None)
                or "unknown"
            )
    return config.ai_model or "unknown"


def resolve_language(config: AnalysisConfig) -> str:
    """Return the RunConfig language for cache fingerprints, or "" if unset.

    The empty string, not None, is what "language not provided" looks like
    on the wire; it must round-trip through the subprocess unchanged.
    """
    rc = config.run_config
    if rc is not None:
        return getattr(rc, "language", "") or ""
    return ""


def resolve_standards_dir(config: AnalysisConfig) -> Path | None:
    """Return the standards ROOT (``RunConfig.standards_dir``) for the
    subprocess's cache-writer keying, or None when no RunConfig is carried.

    This is deliberately NOT ``config.compiled_dir``: that field is already
    ``standards_dir / "compiled"`` (see ``_dimension_steps.py`` /
    ``_pool_launcher.py``), and ``build_cache_writer`` /
    ``dimension_params_state`` append ``"compiled/<dim>.json"`` themselves.
    Passing ``compiled_dir`` here would double the ``compiled`` segment,
    silently missing the params fingerprint (see final-review fix notes on
    ``findings_server.main``).
    """
    rc = config.run_config
    if rc is not None:
        sd = getattr(rc, "standards_dir", None)
        if sd is not None:
            return Path(sd)
    return None
