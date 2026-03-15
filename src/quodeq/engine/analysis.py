"""AI CLI subprocess runner -- spawns the AI CLI, captures stream-json, extracts JSONL."""
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

from quodeq.engine.analysis_stream import (
    count_files_in_stream,
    count_jsonl_lines,
)
from quodeq.engine._progress_reader import _IncrementalProgressReader
from quodeq.shared.logging import log_debug, log_warning
from quodeq.shared.utils import get_ai_cmd, get_ai_model

HeartbeatCallback = Callable[[int, dict], None]


_DEFAULT_MAX_TURNS = 200
_DEFAULT_MAX_DURATION = 1800  # 30 minutes
_TERMINATE_TIMEOUT_S = 10


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
    compiled_dir: Path | None = None
    dimension: str | None = None
    queue_path: Path | None = None
    agent_id: str = ""


def _create_mcp_config(
    jsonl_file: Path,
    compiled_dir: Path | None = None,
    dimension: str | None = None,
    queue_path: Path | None = None,
    agent_id: str = "",
) -> Path:
    """Create a temporary MCP config file pointing to the findings server."""
    mcp_script = str(Path(__file__).resolve().parent / "mcp_findings.py")
    mcp_args = [mcp_script, str(jsonl_file.resolve())]
    if compiled_dir and dimension:
        mcp_args.extend(["--compiled-dir", str(compiled_dir.resolve()), "--dimension", dimension])
    if queue_path:
        mcp_args.extend(["--queue", str(queue_path.resolve())])
    if agent_id:
        mcp_args.extend(["--agent-id", agent_id])
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
    """Return the comma-separated list of AI tools to enable.

    Reads QUODEQ_AI_TOOLS from the environment (default: "Glob,Grep,Read").
    """
    return (env or os.environ).get("QUODEQ_AI_TOOLS", _DEFAULT_AI_TOOLS)


def _get_base_ai_args(env: dict[str, str] | None = None) -> tuple[str, ...]:
    """Return base CLI arguments for the AI subprocess.

    Reads QUODEQ_AI_BASE_ARGS from the environment
    (default: "--print --output-format stream-json --verbose").
    """
    return tuple((env or os.environ).get("QUODEQ_AI_BASE_ARGS", _DEFAULT_BASE_AI_ARGS).split())

_AI_PROVIDERS_PATH = Path(__file__).resolve().parent.parent / "data" / "config" / "ai_providers.json"

_PROVIDER_CONFIGS_FALLBACK: dict[str, dict] = {
    "claude": {
        "mcp_permission_args": ["--permission-mode", "bypassPermissions"],
        "env_set_if_missing": {"CODEX_SANDBOX": "read-only"},
        "env_remove": ["CLAUDECODE"],
    },
    "codex": {
        "mcp_permission_args": [],
        "env_set_if_missing": {"CODEX_SANDBOX": "read-only"},
        "env_remove": [],
    },
}


def _load_provider_configs() -> dict[str, dict]:
    """Load AI provider configs from external JSON, falling back to built-in defaults."""
    try:
        return json.loads(_AI_PROVIDERS_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return _PROVIDER_CONFIGS_FALLBACK


_PROVIDER_CONFIGS: dict[str, dict] = _load_provider_configs()


class AnalysisError(RuntimeError):
    """Raised when the AI CLI subprocess fails (non-zero exit, auth error, etc.)."""


def _build_ai_cmd(
    prompt: str, config: AnalysisConfig,
) -> tuple[list[str], Path | None]:
    """Build the AI CLI command line and optional MCP config path."""
    cmd = config.ai_cmd or get_ai_cmd()
    model = config.ai_model or get_ai_model()

    args = [cmd, *_get_base_ai_args(), "--tools", _get_ai_tools()]

    provider_cfg = _PROVIDER_CONFIGS.get(cmd, {})
    mcp_config_path: Path | None = None
    if config.jsonl_file is not None:
        mcp_config_path = _create_mcp_config(
            config.jsonl_file, config.compiled_dir, config.dimension,
            config.queue_path, config.agent_id,
        )
        args.extend(["--mcp-config", str(mcp_config_path)])
        allowed = "mcp__findings__report_finding"
        if config.queue_path:
            allowed += ",mcp__findings__get_next_files"
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


def _build_analysis_env(ai_cmd: str | None = None) -> dict[str, str]:
    """Build the subprocess environment for the AI CLI."""
    env = os.environ.copy()
    provider_cfg = _PROVIDER_CONFIGS.get(ai_cmd or "", {})
    for key, val in provider_cfg.get("env_set_if_missing", {}).items():
        if key not in env:
            env[key] = val
    for key in provider_cfg.get("env_remove", []):
        env.pop(key, None)
    return env


_SENSITIVE_PATTERNS = re.compile(
    r"(api[_-]?key|token|secret|password|authorization)[=:\s]+\S+",
    re.IGNORECASE,
)


def _sanitize_stderr(text: str) -> str:
    """Remove potential secrets from stderr output before including in errors."""
    return _SENSITIVE_PATTERNS.sub(r"\1=***", text)


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


def run_analysis(
    work_dir: Path, prompt: str, stream_file: Path,
    config: AnalysisConfig | None = None,
) -> None:
    """Spawn AI CLI subprocess, capturing stream-json to *stream_file*."""
    cfg = config or AnalysisConfig()
    args, mcp_config_path = _build_ai_cmd(prompt, cfg)
    env = _build_analysis_env(cfg.ai_cmd or get_ai_cmd())
    stream_err = Path(str(stream_file) + ".err")

    try:
        with open(stream_file, "w") as out, open(stream_err, "w") as err:
            process = subprocess.Popen(
                args, cwd=str(work_dir), env=env,
                stdout=out, stderr=err, stdin=subprocess.DEVNULL,
            )
            timed_out = _run_with_heartbeat(process, cfg, stream_file)
    finally:
        if mcp_config_path is not None:
            mcp_config_path.unlink(missing_ok=True)

    # When terminated by timeout, the evidence collected so far is still valid
    # (MCP server writes findings to JSONL in real time). Skip the error check
    # so the pipeline can score whatever was gathered before the cutoff.
    if not timed_out:
        _check_process_result(process, stream_err)
