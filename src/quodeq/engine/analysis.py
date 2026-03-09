"""AI CLI subprocess runner and stream-json evidence extractor.

Spawns the AI CLI with codebase exploration tools (Bash, Glob, Grep, Read),
captures stream-json output, and extracts JSONL evidence lines.
Uses an MCP tool server so findings stream in real time via tool calls.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from quodeq.utils import get_ai_cmd, get_ai_model


@dataclass(frozen=True)
class AnalysisConfig:
    """Configuration for an AI CLI analysis run."""
    jsonl_file: Path | None = None
    analysis_budget: str | None = None
    heartbeat_interval: int = 10
    heartbeat_callback: object | None = None
    ai_cmd: str | None = None
    ai_model: str | None = None


# ---------------------------------------------------------------------------
# MCP config for real-time findings
# ---------------------------------------------------------------------------

def _create_mcp_config(jsonl_file: Path) -> Path:
    """Create a temporary MCP config file pointing to the findings server."""
    mcp_script = str(Path(__file__).resolve().parent / "mcp_findings.py")
    jsonl_path = str(jsonl_file.resolve())
    config = {
        "mcpServers": {
            "findings": {
                "command": sys.executable,
                "args": [mcp_script, jsonl_path],
            }
        }
    }
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="mcp_findings_", delete=False,
    )
    json.dump(config, tmp)
    tmp.close()
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# AI CLI subprocess
# ---------------------------------------------------------------------------



def _count_jsonl_lines(jsonl_file: Path) -> int:
    """Count evidence lines in the JSONL file written by the MCP server."""
    try:
        if not jsonl_file.exists():
            return 0
        return sum(1 for line in jsonl_file.read_text().splitlines() if line.strip())
    except OSError:
        return 0


def _extract_files_from_assistant_event(data: dict) -> set[str]:
    """Extract file paths from Read/Grep tool_use blocks in an assistant event."""
    files: set[str] = set()
    for block in data.get("message", {}).get("content", []):
        if block.get("type") == "tool_use" and block.get("name") in ("Read", "Grep"):
            fp = (block.get("input") or {}).get("file_path") or (block.get("input") or {}).get("path")
            if fp:
                files.add(fp)
    return files


def _extract_files_from_item_completed_event(data: dict) -> set[str]:
    """Extract file paths from Read/Grep tool_use blocks in an item.completed event."""
    files: set[str] = set()
    item = data.get("item", {})
    for block in item.get("content", []):
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") in ("Read", "Grep"):
            fp = (block.get("input") or {}).get("file_path") or (block.get("input") or {}).get("path")
            if fp:
                files.add(fp)
    return files


def _count_files_from_stream(stream_file: Path) -> set[str]:
    """Extract unique file paths from Read/Grep tool_use events in the stream."""
    files: set[str] = set()
    try:
        with open(stream_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                etype = data.get("type", "")
                if etype == "assistant":
                    files.update(_extract_files_from_assistant_event(data))
                elif etype == "item.completed":
                    files.update(_extract_files_from_item_completed_event(data))
    except (OSError, ValueError):
        pass
    return files


def _count_stream_progress(stream_file: Path, jsonl_file: Path | None = None) -> dict:
    """Count files read (from stream) and evidence found (from JSONL or stream)."""
    files = _count_files_from_stream(stream_file)
    if jsonl_file is not None:
        evidence_count = _count_jsonl_lines(jsonl_file)
    else:
        evidence_count = 0
    return {"files_read": len(files), "evidence": evidence_count}


def count_files_from_stream(stream_file: Path) -> int:
    """Public: count unique files read by the AI from the stream file."""
    return len(_count_files_from_stream(stream_file))


class AnalysisError(RuntimeError):
    """Raised when the AI CLI subprocess fails (non-zero exit, auth error, etc.)."""


def _build_ai_cmd(
    prompt: str,
    *,
    ai_cmd: str | None = None,
    ai_model: str | None = None,
    jsonl_file: Path | None = None,
    analysis_budget: str | None = None,
) -> tuple[list[str], Path | None]:
    """Build the AI CLI command line and optional MCP config path.

    Returns (args_list, mcp_config_path_or_None).
    """
    cmd = ai_cmd or get_ai_cmd()
    model = ai_model or get_ai_model()
    tools = "Bash,Glob,Grep,Read"

    args = [cmd, "--print", "--output-format", "stream-json", "--verbose", "--tools", tools]

    mcp_config_path: Path | None = None
    if jsonl_file is not None:
        mcp_config_path = _create_mcp_config(jsonl_file)
        args.extend(["--mcp-config", str(mcp_config_path)])
        args.extend(["--allowedTools", "mcp__findings__report_finding"])
        # MCP servers require permission approval; in --print mode there is no
        # interactive prompt, so we must bypass permissions for the server to start.
        args.extend(["--permission-mode", "bypassPermissions"])

    if model:
        args.extend(["--model", model])
    if analysis_budget:
        args.extend(["--max-budget-usd", str(analysis_budget)])
    args.extend(["-p", prompt])

    return args, mcp_config_path


def _run_with_heartbeat(
    process: subprocess.Popen,
    heartbeat_interval: int,
    heartbeat_callback: object | None,
    stream_file: Path,
    jsonl_file: Path | None,
) -> None:
    """Wait for process to finish, emitting heartbeat callbacks at intervals."""
    elapsed = 0
    while process.poll() is None:
        try:
            process.wait(timeout=heartbeat_interval)
        except subprocess.TimeoutExpired:
            elapsed += heartbeat_interval
            if heartbeat_callback:
                progress = _count_stream_progress(stream_file, jsonl_file)
                heartbeat_callback(elapsed, progress)


def _build_analysis_env() -> dict[str, str]:
    """Build the subprocess environment for the AI CLI."""
    env = os.environ.copy()
    if "CODEX_SANDBOX" not in env:
        env["CODEX_SANDBOX"] = "read-only"
    env.pop("CLAUDECODE", None)
    return env


def _check_process_result(process: subprocess.Popen, stream_err: Path) -> None:
    """Raise AnalysisError if the process exited with a non-zero code."""
    if process.returncode != 0:
        stderr_text = ""
        if stream_err.exists():
            stderr_text = stream_err.read_text().strip()
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
    args, mcp_config_path = _build_ai_cmd(
        prompt, ai_cmd=cfg.ai_cmd, ai_model=cfg.ai_model,
        jsonl_file=cfg.jsonl_file, analysis_budget=cfg.analysis_budget,
    )
    env = _build_analysis_env()
    stream_err = Path(str(stream_file) + ".err")

    try:
        with open(stream_file, "w") as out, open(stream_err, "w") as err:
            process = subprocess.Popen(
                args, cwd=str(work_dir), env=env,
                stdout=out, stderr=err, stdin=subprocess.DEVNULL,
            )
            _run_with_heartbeat(process, cfg.heartbeat_interval, cfg.heartbeat_callback, stream_file, cfg.jsonl_file)
    finally:
        if mcp_config_path is not None:
            mcp_config_path.unlink(missing_ok=True)

    _check_process_result(process, stream_err)


