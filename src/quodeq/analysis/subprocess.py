"""AI analysis runner -- dispatches to CLI subprocess or API runner.

This module is the public entry point. Implementation is split across:
- _config.py:               AnalysisConfig, HeartbeatCallback, dataclasses
- _mcp_config.py:            MCP config file creation
- _command.py:               CLI argument and environment construction
- _mcp_arg_builders.py:      MCP/tool/model arg construction for _command.py
- _process.py:               Process spawning, heartbeat, error handling
- _api_runner.py:            OpenAI SDK-based direct API runner
- _api_standards_text.py:    Source-file gathering + compiled standards text
                              for the API prompt
- _api_source_gathering.py:  Credential loaders + queue-aware file batching
                              for the API runner
- _api_batch.py:             Per-dimension batch context and the sub-batch
                              dispatch loop for the API runner
"""
from __future__ import annotations

import logging
import tempfile
from contextlib import ExitStack
from collections.abc import Mapping
from pathlib import Path

from quodeq.analysis._api_batch import (
    build_api_batch_context,
    build_batch_api_config,
    dispatch_api_batches,
)
from quodeq.analysis._api_source_gathering import (
    batch_files_by_size,  # noqa: F401 -- re-export
    CREDENTIAL_LOADERS,
    gather_api_source_files,  # noqa: F401 -- re-export
    write_stream_done_marker,
)
from quodeq.analysis._api_standards_text import (
    gather_source_files,  # noqa: F401 -- re-export
    load_standards_text,  # noqa: F401 -- re-export
    render_standards_grouped,  # noqa: F401 -- re-export
    SKIP_DIRS,  # noqa: F401 -- re-export
)
from quodeq.analysis._command import (
    build_ai_cmd,
    build_analysis_env,
    register_cli_mcp,
)
from quodeq.analysis._config import AnalysisConfig, HeartbeatCallback, SpawnPaths
from quodeq.analysis._process import AnalysisError, check_process_result, spawn_and_monitor
from quodeq.analysis.provider_cache import get_provider_configs
from quodeq.analysis.stream.counters import count_files_in_stream
from quodeq.analysis.errors import FatalProviderError, classify_fatal_provider_message
from quodeq.config.process_env import process_environment
from quodeq.config.provider import Provider
from quodeq.core.constants import MCP_STYLE_CLI_REGISTER, MCP_STYLE_CONFIG_FILE
from quodeq.core.stream.events import copilot_error, parse_stream_event
from quodeq.shared.utils import sanitize_sensitive
from quodeq.shared.utils import get_ai_cmd


_log = logging.getLogger(__name__)

# Re-export public API so existing imports keep working
__all__ = [
    "AnalysisConfig",
    "AnalysisError",
    "HeartbeatCallback",
    "count_files_from_stream",
    "run_analysis",
    "build_ai_cmd",
]


def count_files_from_stream(stream_file: Path) -> int:
    """Public: count unique files read by the AI from the stream file."""
    return len(count_files_in_stream(stream_file))


def get_provider_type(ai_cmd: str) -> str:
    """Determine the provider type (cli or api) from the provider config."""
    configs = get_provider_configs()
    provider_cfg = configs.get(ai_cmd, {})
    return provider_cfg.get("type", "cli")


def _run_cli_analysis(
    work_dir: Path, prompt: str, stream_file: Path, cfg: AnalysisConfig,
) -> None:
    """Run analysis via CLI subprocess."""
    ai_cmd = cfg.ai_cmd or get_ai_cmd()
    # ai_cmd comes from the AI_CMD/AI_PROVIDER env var and is gated to known
    # providers in register_cli_mcp before any subprocess call; it runs via a
    # subprocess list (no shell injection). Skipping shutil.which for CI/PATH.
    configs = get_provider_configs()
    provider_cfg = configs.get(ai_cmd, {})
    mcp_style = provider_cfg.get("mcp_style", MCP_STYLE_CONFIG_FILE)

    # For cli-register providers (e.g. Gemini), register MCP server before the run.
    # Registration is shared across all parallel agents — the first agent registers,
    # and we never unregister during the run (cleanup happens at pool level).
    if mcp_style == MCP_STYLE_CLI_REGISTER and cfg.jsonl_file is not None:
        register_cli_mcp(ai_cmd, cfg, work_dir)

    args, mcp_config_path = build_ai_cmd(prompt, cfg, work_dir=work_dir)
    stream_err = Path(str(stream_file) + ".err")

    try:
        env = build_analysis_env(ai_cmd)
        with ExitStack() as stack:
            cwd = work_dir
            if ai_cmd == Provider.COPILOT:
                cwd = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="quodeq-copilot-")))
            process, timed_out = spawn_and_monitor(
                args, cwd, env, SpawnPaths(stream_file, stream_err), cfg,
            )
    finally:
        if mcp_config_path is not None:
            mcp_config_path.unlink(missing_ok=True)
        # Don't unregister cli MCP here — other parallel agents may still need it.
        # Cleanup happens via register_cli_mcp's idempotent remove-then-add on next run.

    if not timed_out:
        if ai_cmd == Provider.COPILOT:
            _check_copilot_stream(stream_file)
        check_process_result(process, stream_err)


def _check_copilot_stream(stream_file: Path) -> None:
    """Copilot reports provider errors on stdout, including some zero-exit failures."""
    with stream_file.open(encoding="utf-8") as stream:
        for line in stream:
            event = parse_stream_event(line)
            error = copilot_error(event) if isinstance(event, dict) else None
            if error:
                message, reason = error
                message = sanitize_sensitive(message)
                reason = reason or classify_fatal_provider_message(message)
                if reason:
                    raise FatalProviderError(message, reason=reason)
                raise AnalysisError(message)


def _resolve_provider_config(
    cfg: AnalysisConfig, env: Mapping[str, str],
) -> tuple[str, str, str]:
    """Look up model, api_base, and api_key from provider config.

    Credentials come from *env*, injected by the public entry point
    (``run_analysis``) so this resolution logic never touches process-global
    environment state itself.

    Raises AnalysisError if model or api_base are missing.
    """
    ai_cmd = cfg.ai_cmd or get_ai_cmd()
    configs = get_provider_configs()
    provider_cfg = configs.get(ai_cmd, {})

    model = cfg.ai_model or provider_cfg.get("model", "")
    api_base = provider_cfg.get("api_base", "")
    api_key_env = provider_cfg.get("api_key_env", "")
    api_key = env.get(api_key_env, "") if api_key_env else ""
    if not api_key:
        loader = CREDENTIAL_LOADERS.get(ai_cmd)
        if loader is not None:
            api_key = loader(env) or ""

    if not model:
        raise AnalysisError(
            f"No model configured for provider '{ai_cmd}'. "
            f"Go to Settings in the dashboard to select a model, or set AI_MODEL in your environment."
        )
    if not api_base:
        raise AnalysisError(
            f"No API base URL configured for provider '{ai_cmd}'. "
            f"Go to Settings in the dashboard to configure it, or set the URL in ai_providers.json."
        )
    if not api_key and provider_cfg.get("api_key_required"):
        # Defense in depth for entry points that skip check_evaluate_prereqs:
        # fail with a clear message instead of 401s on every request mid-run.
        raise AnalysisError(
            f"No API key found for provider '{ai_cmd}'. "
            f"Set the {api_key_env or 'API key'} environment variable, "
            f"or configure the key in the dashboard Settings."
        )
    return model, api_base, api_key


def _run_api_analysis_bridge(
    work_dir: Path, stream_file: Path, cfg: AnalysisConfig,
    env: Mapping[str, str],
) -> None:
    """Run analysis for an api provider by calling the model directly.

    Builds its own prompt using assemble_api_prompt() instead of the CLI
    prompt, which contains MCP tool-use instructions that confuse API models.
    Files are dispatched in size-budgeted sub-batches (one model call each)
    so a batch of large files cannot overflow the model context.
    """
    model, api_base, api_key = _resolve_provider_config(cfg, env)
    ctx = build_api_batch_context(work_dir, cfg, env, stream_file)
    if ctx is None:
        return

    api_config = build_batch_api_config(cfg, model, api_base, api_key)
    dispatch_api_batches(ctx, cfg, api_config, env)

    write_stream_done_marker(stream_file)
    _log.debug("API analysis complete, evidence written to %s", ctx.jsonl_file)


def run_analysis(
    work_dir: Path, prompt: str, stream_file: Path,
    config: AnalysisConfig | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    """Run AI analysis, dispatching to CLI or API runner based on provider type.

    *env* supplies provider credentials; the default is resolved here, at the
    public boundary, so the resolution logic below stays injectable.
    """
    cfg = config or AnalysisConfig()
    ai_cmd = cfg.ai_cmd or get_ai_cmd()
    provider_type = get_provider_type(ai_cmd)

    if provider_type == "api":
        _run_api_analysis_bridge(work_dir, stream_file, cfg, process_environment(env))
    else:
        _run_cli_analysis(work_dir, prompt, stream_file, cfg)
