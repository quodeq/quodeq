"""AI CLI subprocess runner and stream-json evidence extractor.

Spawns the AI CLI with codebase exploration tools (Bash, Glob, Grep, Read),
captures stream-json output, and extracts JSONL evidence lines.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# AI CLI subprocess
# ---------------------------------------------------------------------------

def _get_ai_cmd() -> str:
    return os.environ.get("AI_CMD", "claude")


def _get_ai_model() -> str | None:
    return os.environ.get("AI_MODEL") or None


def _count_stream_progress(stream_file: Path) -> dict:
    """Read the stream file so far and count files read + evidence found."""
    files_read: set[str] = set()
    evidence_count = 0
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
                    for block in data.get("message", {}).get("content", []):
                        if block.get("type") == "tool_use" and block.get("name") == "Read":
                            fp = block.get("input", {}).get("file_path")
                            if fp:
                                files_read.add(fp)
                        elif block.get("type") == "text":
                            for tl in block.get("text", "").splitlines():
                                tl = tl.strip()
                                if tl.startswith("{"):
                                    try:
                                        obj = json.loads(tl)
                                        if obj.get("p") and obj.get("t") in ("violation", "compliance"):
                                            evidence_count += 1
                                    except json.JSONDecodeError:
                                        pass
                elif etype == "item.completed":
                    item = data.get("item", {})
                    for block in item.get("content", []):
                        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Read":
                            fp = block.get("input", {}).get("file_path")
                            if fp:
                                files_read.add(fp)
    except (OSError, ValueError):
        pass
    return {"files_read": len(files_read), "evidence": evidence_count}


def run_analysis(
    work_dir: Path,
    prompt: str,
    stream_file: Path,
    *,
    analysis_budget: str | None = None,
    heartbeat_interval: int = 60,
    heartbeat_callback: object | None = None,
) -> None:
    """Spawn AI CLI subprocess with tools, capturing stream-json to *stream_file*.

    Args:
        work_dir: Repository directory to analyse.
        prompt: Full analysis prompt text.
        stream_file: Path to write stream-json output.
        analysis_budget: Optional max budget in USD.
        heartbeat_interval: Seconds between heartbeat callbacks.
        heartbeat_callback: Optional callable(elapsed_seconds, progress) for progress.
    """
    cmd = _get_ai_cmd()
    model = _get_ai_model()
    tools = "Bash,Glob,Grep,Read"

    args = [cmd, "--print", "--output-format", "stream-json", "--verbose", "--tools", tools]
    if model:
        args.extend(["--model", model])
    if analysis_budget:
        args.extend(["--max-budget-usd", str(analysis_budget)])
    args.extend(["-p", prompt])

    env = os.environ.copy()
    if "CODEX_SANDBOX" not in env:
        env["CODEX_SANDBOX"] = "read-only"
    env.pop("CLAUDECODE", None)

    stream_err = Path(str(stream_file) + ".err")
    with open(stream_file, "w") as out, open(stream_err, "w") as err:
        process = subprocess.Popen(
            args,
            cwd=str(work_dir),
            env=env,
            stdout=out,
            stderr=err,
            stdin=subprocess.DEVNULL,
        )
        elapsed = 0
        while process.poll() is None:
            try:
                process.wait(timeout=heartbeat_interval)
            except subprocess.TimeoutExpired:
                elapsed += heartbeat_interval
                if heartbeat_callback:
                    progress = _count_stream_progress(stream_file)
                    heartbeat_callback(elapsed, progress)


# ---------------------------------------------------------------------------
# JSONL extraction from stream-json
# ---------------------------------------------------------------------------

def _extract_jsonl_from_text(text: str, out) -> tuple[int, int]:
    """Scan text for JSONL evidence objects.

    Returns (evidence_count, total_lines_scanned).
    """
    count = 0
    lines = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        lines += 1
        if line.startswith("```"):
            continue
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                if obj.get("p") and obj.get("t") in ("violation", "compliance"):
                    out.write(line + "\n")
                    count += 1
            except json.JSONDecodeError:
                pass
    return count, lines


def _process_assistant_event(data: dict, out, stats: dict, files_read: set) -> None:
    msg = data.get("message", {})
    for block in msg.get("content", []):
        btype = block.get("type")
        if btype == "text":
            text = block["text"].strip()
            if text:
                stats["text_blocks"] += 1
                c, l = _extract_jsonl_from_text(text, out)
                stats["jsonl_lines"] += c
                stats["total_text_lines"] += l
        elif btype == "tool_use" and block.get("name") == "Read":
            fp = block.get("input", {}).get("file_path")
            if fp:
                files_read.add(fp)


def _process_result_event(data: dict, out, stats: dict) -> None:
    result = data.get("result", "").strip()
    if result:
        stats["text_blocks"] += 1
        c, l = _extract_jsonl_from_text(result, out)
        stats["jsonl_lines"] += c
        stats["total_text_lines"] += l


def _process_item_completed_event(data: dict, out, stats: dict, files_read: set) -> None:
    item = data.get("item", {})
    if item.get("type") == "agent_message":
        text = (item.get("text") or "").strip()
        if text:
            stats["text_blocks"] += 1
            c, l = _extract_jsonl_from_text(text, out)
            stats["jsonl_lines"] += c
            stats["total_text_lines"] += l
        for block in item.get("content", []):
            if isinstance(block, dict):
                btype = block.get("type")
                if btype in ("text", "output_text"):
                    block_text = (block.get("text") or "").strip()
                    if block_text:
                        stats["text_blocks"] += 1
                        c, l = _extract_jsonl_from_text(block_text, out)
                        stats["jsonl_lines"] += c
                        stats["total_text_lines"] += l
                elif btype == "tool_use" and block.get("name") == "Read":
                    fp = block.get("input", {}).get("file_path")
                    if fp:
                        files_read.add(fp)


def extract_evidence_from_stream(stream_file: Path, jsonl_file: Path) -> int:
    """Parse stream-json events and extract JSONL evidence lines.

    Args:
        stream_file: Path to the stream-json file from AI CLI.
        jsonl_file: Path to write extracted JSONL evidence.

    Returns:
        Number of unique files read by the AI during analysis.
    """
    stats: dict = {"text_blocks": 0, "jsonl_lines": 0, "total_text_lines": 0}
    files_read: set = set()

    with open(stream_file) as f, open(jsonl_file, "w") as out:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = data.get("type", "unknown")

            if etype == "assistant":
                _process_assistant_event(data, out, stats, files_read)
            elif etype == "result":
                _process_result_event(data, out, stats)
            elif etype == "item.completed":
                _process_item_completed_event(data, out, stats, files_read)

    return len(files_read)


# ---------------------------------------------------------------------------
# Stream validation
# ---------------------------------------------------------------------------

def is_stream_valid(stream_file: Path) -> bool:
    """Return True if stream has no error events. Empty/missing files are valid."""
    path = Path(stream_file)
    if not path.exists() or path.stat().st_size == 0:
        return True
    with open(path) as f:
        for line in f:
            try:
                d = json.loads(line.strip())
                if d.get("type") == "result" and d.get("is_error"):
                    return False
            except json.JSONDecodeError:
                pass
    return True
