"""AI CLI subprocess runner -- spawns the AI CLI, captures stream-json.

This module is the public entry point. Implementation is split across:
- _config.py:     AnalysisConfig, HeartbeatCallback, dataclasses
- _mcp_config.py: MCP config file creation
- _command.py:    CLI argument and environment construction
- _process.py:    Process spawning, heartbeat, error handling
"""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis._command import _build_ai_cmd, _build_analysis_env
from quodeq.analysis._config import AnalysisConfig, HeartbeatCallback, _SpawnPaths
from quodeq.analysis._process import AnalysisError, _check_process_result, _spawn_and_monitor
from quodeq.analysis.stream.counters import count_files_in_stream
from quodeq.shared.utils import get_ai_cmd

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


def run_analysis(
    work_dir: Path, prompt: str, stream_file: Path,
    config: AnalysisConfig | None = None,
) -> None:
    """Spawn AI CLI subprocess, capturing stream-json to *stream_file*."""
    cfg = config or AnalysisConfig()
    args, mcp_config_path = _build_ai_cmd(prompt, cfg, work_dir=work_dir)
    env = _build_analysis_env(cfg.ai_cmd or get_ai_cmd())
    stream_err = Path(str(stream_file) + ".err")

    try:
        process, timed_out = _spawn_and_monitor(args, work_dir, env, _SpawnPaths(stream_file, stream_err), cfg)
    finally:
        if mcp_config_path is not None:
            mcp_config_path.unlink(missing_ok=True)

    if not timed_out:
        _check_process_result(process, stream_err)
