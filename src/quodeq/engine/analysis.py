"""AI CLI subprocess runner and stream-json evidence extractor.

Spawns the AI CLI with codebase exploration tools (Bash, Glob, Grep, Read),
captures stream-json output, and extracts JSONL evidence lines.
Uses an MCP tool server so findings stream in real time via tool calls.
"""
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


def _create_mcp_config(
    jsonl_file: Path, compiled_dir: Path | None = None, dimension: str | None = None,
) -> Path:
    """Create a temporary MCP config file pointing to the findings server."""
    mcp_script = str(Path(__file__).resolve().parent / "mcp_findings.py")
    mcp_args = [mcp_script, str(jsonl_file.resolve())]
    if compiled_dir and dimension:
        mcp_args.extend(["--compiled-dir", str(compiled_dir.resolve()), "--dimension", dimension])
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
    os.chmod(tmp.name, 0o600)
    json.dump(config, tmp)
    tmp.close()
    return Path(tmp.name)


def _count_jsonl_lines(jsonl_file: Path) -> int:
    """Count evidence lines in the JSONL file written by the MCP server."""
    try:
        if not jsonl_file.exists():
            return 0
        with open(jsonl_file) as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def _extract_files_from_blocks(blocks: list) -> set[str]:
    """Extract file paths from Read/Grep tool_use blocks."""
    files: set[str] = set()
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") in ("Read", "Grep"):
            fp = (block.get("input") or {}).get("file_path") or (block.get("input") or {}).get("path")
            if fp:
                files.add(fp)
    return files


def _parse_stream_event(line: str) -> dict | None:
    """Parse a single stream event line, returning None for empty or invalid lines."""
    stripped = line.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def _extract_files_from_event(data: dict) -> set[str]:
    """Dispatch to the appropriate file extractor based on event type."""
    etype = data.get("type", "")
    if etype == "assistant":
        return _extract_files_from_blocks(data.get("message", {}).get("content", []))
    if etype == "item.completed":
        return _extract_files_from_blocks(data.get("item", {}).get("content", []))
    return set()


def _count_files_from_stream(stream_file: Path) -> set[str]:
    """Extract unique file paths from Read/Grep tool_use events in the stream."""
    files: set[str] = set()
    try:
        with open(stream_file) as f:
            for line in f:
                data = _parse_stream_event(line)
                if data is not None:
                    files.update(_extract_files_from_event(data))
    except (OSError, ValueError) as exc:
        log_debug(f"Failed to count files from stream {stream_file}: {exc}")
    return files


def _count_stream_progress(stream_file: Path, jsonl_file: Path | None = None) -> dict:
    """Count files read (from stream) and evidence found (from JSONL or stream)."""
    files = _count_files_from_stream(stream_file)
    evidence_count = _count_jsonl_lines(jsonl_file) if jsonl_file is not None else 0
    return {"files_read": len(files), "evidence": evidence_count}


def count_files_from_stream(stream_file: Path) -> int:
    """Public: count unique files read by the AI from the stream file."""
    return len(_count_files_from_stream(stream_file))


_AI_TOOLS: str = os.environ.get("QUODEQ_AI_TOOLS", "Bash,Glob,Grep,Read")
_BASE_AI_ARGS: tuple[str, ...] = tuple(
    os.environ.get("QUODEQ_AI_BASE_ARGS", "--print --output-format stream-json --verbose").split()
)

# Provider-keyed configuration: extend this dict to add support for a new AI
# provider without modifying _build_ai_cmd or _build_analysis_env.
_PROVIDER_CONFIGS: dict[str, dict] = {
    "claude": {
        # Extra CLI flags added when an MCP config is present.
        "mcp_permission_args": ["--permission-mode", "bypassPermissions"],
        # Env vars set when not already present in the subprocess environment.
        "env_set_if_missing": {"CODEX_SANDBOX": "read-only"},
        # Env vars removed from the subprocess environment.
        "env_remove": ["CLAUDECODE"],
    },
    "codex": {
        "mcp_permission_args": [],
        "env_set_if_missing": {"CODEX_SANDBOX": "read-only"},
        "env_remove": [],
    },
}


class AnalysisError(RuntimeError):
    """Raised when the AI CLI subprocess fails (non-zero exit, auth error, etc.)."""


def _build_ai_cmd(
    prompt: str,
    config: AnalysisConfig,
) -> tuple[list[str], Path | None]:
    """Build the AI CLI command line and optional MCP config path.

    Returns (args_list, mcp_config_path_or_None).
    """
    cmd = config.ai_cmd or get_ai_cmd()
    model = config.ai_model or get_ai_model()

    args = [cmd, *_BASE_AI_ARGS, "--tools", _AI_TOOLS]

    provider_cfg = _PROVIDER_CONFIGS.get(cmd, {})
    mcp_config_path: Path | None = None
    if config.jsonl_file is not None:
        mcp_config_path = _create_mcp_config(config.jsonl_file, config.compiled_dir, config.dimension)
        args.extend(["--mcp-config", str(mcp_config_path)])
        args.extend(["--allowedTools", "mcp__findings__report_finding"])
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

    Uses an incremental byte-offset reader so each heartbeat only processes
    new bytes appended since the last read, avoiding repeated full-file scans.
    """
    elapsed = 0
    max_dur = config.max_duration
    timed_out = False
    _stream_offset = 0
    _seen_files: set[str] = set()
    _jsonl_offset = 0
    _jsonl_count = 0

    def _read_stream_incremental() -> dict:
        nonlocal _stream_offset, _jsonl_offset, _jsonl_count
        try:
            with open(stream_file, "rb") as f:
                f.seek(_stream_offset)
                new_bytes = f.read()
                _stream_offset += len(new_bytes)
            for line in new_bytes.decode("utf-8", errors="replace").splitlines():
                data = _parse_stream_event(line)
                if data is not None:
                    _seen_files.update(_extract_files_from_event(data))
        except (OSError, ValueError) as exc:
            log_debug(f"Failed to read stream {stream_file}: {exc}")
        if config.jsonl_file is not None and config.jsonl_file.exists():
            try:
                with open(config.jsonl_file, "rb") as jf:
                    jf.seek(_jsonl_offset)
                    new_bytes_j = jf.read()
                    _jsonl_offset += len(new_bytes_j)
                _jsonl_count += sum(
                    1 for line in new_bytes_j.decode("utf-8", errors="replace").splitlines()
                    if line.strip()
                )
            except OSError:
                pass
        return {"files_read": len(_seen_files), "evidence": _jsonl_count}

    while process.poll() is None:
        try:
            process.wait(timeout=config.heartbeat_interval)
        except subprocess.TimeoutExpired:
            elapsed += config.heartbeat_interval
            if config.heartbeat_callback:
                progress = _read_stream_incremental()
                config.heartbeat_callback(elapsed, progress)
            if max_dur is not None and elapsed >= max_dur:
                log_warning(f"Analysis exceeded max duration ({max_dur}s) — terminating")
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
            stderr_text = _sanitize_stderr(stream_err.read_text().strip())
        raise AnalysisError(
            f"AI CLI exited with code {process.returncode}"
            + (f": {stderr_text}" if stderr_text else "")
        )


def run_analysis(
    work_dir: Path,
    prompt: str,
    stream_file: Path,
    config: AnalysisConfig | None = None,
) -> None:
    """Spawn AI CLI subprocess with tools, capturing stream-json to *stream_file*.

    When *config.jsonl_file* is provided, an MCP findings server is configured so
    the AI reports findings as tool calls that stream directly to the JSONL file.

    Raises:
        AnalysisError: If the subprocess exits with a non-zero code.
    """
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
