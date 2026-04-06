"""AI analysis runner -- dispatches to CLI subprocess or API runner.

This module is the public entry point. Implementation is split across:
- _config.py:      AnalysisConfig, HeartbeatCallback, dataclasses
- _mcp_config.py:  MCP config file creation
- _command.py:     CLI argument and environment construction
- _process.py:     Process spawning, heartbeat, error handling
- _api_runner.py:  OpenAI SDK-based direct API runner
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from quodeq.analysis._command import _build_ai_cmd, _build_analysis_env
from quodeq.analysis._config import AnalysisConfig, HeartbeatCallback, _SpawnPaths
from quodeq.analysis._process import AnalysisError, _check_process_result, _spawn_and_monitor
from quodeq.analysis._provider_cache import get_provider_configs
from quodeq.analysis.stream.counters import count_files_in_stream
from quodeq.shared.utils import get_ai_cmd

_log = logging.getLogger(__name__)

# Re-export public API so existing imports keep working
__all__ = [
    "AnalysisConfig",
    "AnalysisError",
    "HeartbeatCallback",
    "count_files_from_stream",
    "run_analysis",
    "_build_ai_cmd",
]


def count_files_from_stream(stream_file: Path) -> int:
    """Public: count unique files read by the AI from the stream file."""
    return len(count_files_in_stream(stream_file))


def _get_provider_type(ai_cmd: str) -> str:
    """Determine the provider type (cli or api) from the provider config."""
    configs = get_provider_configs()
    provider_cfg = configs.get(ai_cmd, {})
    return provider_cfg.get("type", "cli")


def _run_cli_analysis(
    work_dir: Path, prompt: str, stream_file: Path, cfg: AnalysisConfig,
) -> None:
    """Run analysis via CLI subprocess (existing behavior)."""
    args, mcp_config_path = _build_ai_cmd(prompt, cfg, work_dir=work_dir)
    env = _build_analysis_env(cfg.ai_cmd or get_ai_cmd())
    stream_err = Path(str(stream_file) + ".err")

    try:
        process, timed_out = _spawn_and_monitor(
            args, work_dir, env, _SpawnPaths(stream_file, stream_err), cfg,
        )
    finally:
        if mcp_config_path is not None:
            mcp_config_path.unlink(missing_ok=True)

    if not timed_out:
        _check_process_result(process, stream_err)


def _run_api_analysis_bridge(
    work_dir: Path, prompt: str, stream_file: Path, cfg: AnalysisConfig,
) -> None:
    """Run analysis via direct API call (new behavior)."""
    from quodeq.analysis._api_runner import run_api_analysis, ApiRunnerConfig

    ai_cmd = cfg.ai_cmd or get_ai_cmd()
    configs = get_provider_configs()
    provider_cfg = configs.get(ai_cmd, {})

    model = cfg.ai_model or provider_cfg.get("model", "")
    api_base = provider_cfg.get("api_base", "")
    api_key_env = provider_cfg.get("api_key_env", "")
    api_key = os.environ.get(api_key_env, "") if api_key_env else ""

    if not model:
        raise AnalysisError(f"No model configured for API provider '{ai_cmd}'")
    if not api_base:
        raise AnalysisError(f"No api_base configured for API provider '{ai_cmd}'")

    jsonl_file = cfg.jsonl_file
    if jsonl_file is None:
        jsonl_file = Path(str(stream_file).replace(".stream", "_evidence.jsonl"))

    run_api_analysis(
        prompt=prompt,
        jsonl_file=jsonl_file,
        config=ApiRunnerConfig(
            model=model,
            api_base=api_base,
            api_key=api_key,
        ),
    )

    # Write a minimal stream file so downstream checks (is_stream_valid) pass
    stream_file.write_text('{"type":"api_runner","status":"complete"}\n')
    _log.info("API analysis complete, evidence written to %s", jsonl_file)


def run_analysis(
    work_dir: Path, prompt: str, stream_file: Path,
    config: AnalysisConfig | None = None,
) -> None:
    """Run AI analysis, dispatching to CLI or API runner based on provider type."""
    cfg = config or AnalysisConfig()
    ai_cmd = cfg.ai_cmd or get_ai_cmd()
    provider_type = _get_provider_type(ai_cmd)

    if provider_type == "api":
        _run_api_analysis_bridge(work_dir, prompt, stream_file, cfg)
    else:
        _run_cli_analysis(work_dir, prompt, stream_file, cfg)
