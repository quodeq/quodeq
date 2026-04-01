"""AI CLI subprocess runner -- spawns the AI CLI, captures stream-json."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from quodeq.analysis._provider_cache import get_provider_configs as _get_provider_configs
from quodeq.analysis.stream.counters import (
    count_files_in_stream,
    count_jsonl_lines,
)
from quodeq.analysis.stream.progress_reader import _IncrementalProgressReader
from quodeq.shared.logging import log_debug, log_warning
from quodeq.shared.utils import get_ai_cmd, get_ai_model, sanitize_sensitive as _sanitize_stderr

HeartbeatCallback = Callable[[int, dict], None]


@dataclass(frozen=True)
class _SpawnPaths:
    """Paths for the AI CLI subprocess stdout/stderr capture files."""
    stream_file: Path
    stream_err: Path


_DEFAULT_MAX_TURNS = 200
_DEFAULT_MAX_DURATION = 1800  # 30 minutes
_TERMINATE_TIMEOUT_S = 10
_MCP_TOOL_REPORT_FINDING = "mcp__findings__report_finding"
_MCP_TOOL_GET_NEXT_FILES = "mcp__findings__get_next_files"


@dataclass(frozen=True)
class AnalysisConfig:
    """Configuration for an AI CLI analysis run."""
    jsonl_file: Path | None = None
    analysis_budget: str | None = None
    heartbeat_interval: int = 10
    heartbeat_callback: HeartbeatCallback | None = None
    ai_cmd: str | None = None
    ai_model: str | None = None
    max_turns: int | None = _DEFAULT_MAX_TURNS
    max_duration: int | None = _DEFAULT_MAX_DURATION
    pool_budget: int = 600
    compiled_dir: Path | None = None
    dimension: str | None = None
    queue_path: Path | None = None
    agent_id: str = ""
    max_files_per_agent: int = 30
    work_dir: Path | None = None


@dataclass(frozen=True)
class _AgentParams:
    """Optional grouping of per-agent MCP config parameters."""
    queue_path: Path | None = None
    agent_id: str = ""
    work_dir: Path | None = None


def _create_mcp_config(
    jsonl_file: Path,
    compiled_dir: Path | None = None,
    dimension: str | None = None,
    agent_params: _AgentParams | None = None,
) -> Path:
    """Create a temporary MCP config file pointing to the findings server."""
    ap = agent_params or _AgentParams()
    mcp_script = str(Path(__file__).resolve().parent / "mcp" / "findings_server.py")
    mcp_args = [mcp_script, str(jsonl_file.resolve())]
    if compiled_dir and dimension:
        mcp_args.extend(["--compiled-dir", str(compiled_dir.resolve()), "--dimension", dimension])
    if ap.queue_path:
        mcp_args.extend(["--queue", str(ap.queue_path.resolve())])
    if ap.agent_id:
        mcp_args.extend(["--agent-id", ap.agent_id])
    if ap.work_dir:
        mcp_args.extend(["--work-dir", str(ap.work_dir.resolve())])
    config = {
        "mcpServers": {
            "findings": {
                "command": sys.executable,
                "args": mcp_args,
            }
        }
    }
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="mcp_findings_", delete=False,
    )
    try:
        os.chmod(tmp.name, 0o600)
        json.dump(config, tmp)
    finally:
        tmp.close()
    return Path(tmp.name)


def count_files_from_stream(stream_file: Path) -> int:
    """Public: count unique files read by the AI from the stream file."""
    return len(count_files_in_stream(stream_file))


_DEFAULT_AI_TOOLS = "Glob,Grep,Read"
_DEFAULT_BASE_AI_ARGS = "--print --output-format stream-json --verbose"

def _get_ai_tools(env: dict[str, str] | None = None) -> str:
    """Return AI tools from QUODEQ_AI_TOOLS env var (default: "Glob,Grep,Read")."""
    return (env or os.environ).get("QUODEQ_AI_TOOLS", _DEFAULT_AI_TOOLS)


def _get_base_ai_args(env: dict[str, str] | None = None) -> tuple[str, ...]:
    """Return base AI CLI args from QUODEQ_AI_BASE_ARGS env var."""
    return tuple((env or os.environ).get("QUODEQ_AI_BASE_ARGS", _DEFAULT_BASE_AI_ARGS).split())

class AnalysisError(RuntimeError):
    """Raised when the AI CLI subprocess fails (non-zero exit, auth error, etc.)."""


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
        # MCP servers require permission approval; in --print mode there is no
        # interactive prompt, so we must bypass permissions for the server to start.
        args.extend(provider_cfg.get("mcp_permission_args", ["--permission-mode", "bypassPermissions"]))

    if model:
        args.extend(["--model", model])
    if config.analysis_budget:
        args.extend(["--max-budget-usd", str(config.analysis_budget)])
    if config.max_turns is not None:
        args.extend(["--max-turns", str(config.max_turns)])
    args.extend(["-p", prompt])

    return args, mcp_config_path


def _terminate_process(process: subprocess.Popen) -> None:
    """Send SIGTERM and escalate to SIGKILL if the process doesn't exit."""
    process.terminate()
    try:
        process.wait(timeout=_TERMINATE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        process.kill()


def _run_with_heartbeat(
    process: subprocess.Popen,
    config: AnalysisConfig,
    stream_file: Path,
) -> bool:
    """Wait for process to finish, emitting heartbeat callbacks at intervals.

    Terminates the process if *max_duration* seconds elapse.
    Returns True if the process was terminated due to timeout.
    """
    elapsed = 0
    timed_out = False
    reader = _IncrementalProgressReader(stream_file, config.jsonl_file)

    while process.poll() is None:
        try:
            process.wait(timeout=config.heartbeat_interval)
        except subprocess.TimeoutExpired:
            elapsed += config.heartbeat_interval
            if config.heartbeat_callback:
                config.heartbeat_callback(elapsed, reader.read_progress())
            if config.max_duration is not None and elapsed >= config.max_duration:
                log_warning(
                    f"Analysis exceeded max duration ({config.max_duration}s) "
                    f"-- terminating. Increase with --max-duration or QUODEQ_MAX_DURATION env var."
                )
                _terminate_process(process)
                timed_out = True
    return timed_out


_SENSITIVE_ENV_KEYS = frozenset({
    "QUODEQ_API_KEY", "DATABASE_URL", "SECRET_KEY",
})

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


def _check_process_result(process: subprocess.Popen, stream_err: Path) -> None:
    """Raise AnalysisError if the process exited with a non-zero code."""
    if process.returncode != 0:
        stderr_text = ""
        if stream_err.exists():
            try:
                stderr_text = _sanitize_stderr(stream_err.read_text().strip())
            except (OSError, UnicodeDecodeError):
                stderr_text = "(stderr unreadable)"
        raise AnalysisError(
            f"AI CLI exited with code {process.returncode}"
            + (f": {stderr_text}" if stderr_text else "")
        )


def _spawn_and_monitor(
    args: list[str], work_dir: Path, env: dict,
    paths: _SpawnPaths, cfg: AnalysisConfig,
) -> tuple[subprocess.Popen, bool]:
    """Spawn the AI CLI process, monitor with heartbeat, return (process, timed_out)."""
    with open(paths.stream_file, "w") as out, open(paths.stream_err, "w") as err:
        process = subprocess.Popen(
            args, cwd=str(work_dir), env=env,
            stdout=out, stderr=err, stdin=subprocess.DEVNULL,
        )
        timed_out = _run_with_heartbeat(process, cfg, paths.stream_file)
    return process, timed_out


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
