from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from codecompass.evaluate.lib.ai_cli_provider import get_ai_cmd, get_ai_model
from codecompass.evaluate.lib.common import log_beat, log_error, log_info, log_success, log_warning


# ---------------------------------------------------------------------------
# JSONL extraction from stream-json output
# ---------------------------------------------------------------------------

def extract_jsonl_from_text(text: str, out) -> tuple[int, int]:
    """Scan text line-by-line for JSONL evidence objects.

    Returns:
        Tuple of (count of evidence lines found, total lines scanned)
    """
    count = 0
    lines = 0
    for tl in text.splitlines():
        tl = tl.strip()
        if not tl:
            continue
        lines += 1
        if tl.startswith("```"):
            continue
        if tl.startswith("{"):
            try:
                obj = json.loads(tl)
                if obj.get("p") and obj.get("t") in ("violation", "compliance"):
                    out.write(tl + "\n")
                    count += 1
            except json.JSONDecodeError:
                pass
    return count, lines


def process_assistant_event(data: dict, out, stats: dict) -> None:
    """Process legacy assistant message events."""
    msg = data.get("message", {})
    for block in msg.get("content", []):
        if block.get("type") == "text":
            text = block["text"].strip()
            if text:
                stats["text_blocks"] += 1
                c, l = extract_jsonl_from_text(text, out)
                stats["jsonl_lines"] += c
                stats["total_text_lines"] += l


def process_result_event(data: dict, out, stats: dict) -> None:
    """Process result events."""
    result = data.get("result", "").strip()
    if result:
        stats["text_blocks"] += 1
        c, l = extract_jsonl_from_text(result, out)
        stats["jsonl_lines"] += c
        stats["total_text_lines"] += l


def process_item_completed_event(data: dict, out, stats: dict) -> None:
    """Process Codex-style item.completed events."""
    item = data.get("item", {})
    if item.get("type") == "agent_message":
        text = (item.get("text") or "").strip()
        if text:
            stats["text_blocks"] += 1
            c, l = extract_jsonl_from_text(text, out)
            stats["jsonl_lines"] += c
            stats["total_text_lines"] += l
        for block in item.get("content", []):
            if isinstance(block, dict) and block.get("type") in ("text", "output_text"):
                block_text = (block.get("text") or "").strip()
                if block_text:
                    stats["text_blocks"] += 1
                    c, l = extract_jsonl_from_text(block_text, out)
                    stats["jsonl_lines"] += c
                    stats["total_text_lines"] += l


def extract_jsonl_evidence(stream_file: str, jsonl_file: str, dimension: str) -> None:
    """Extract JSONL evidence lines from a stream-json file."""
    stats: dict = {"text_blocks": 0, "jsonl_lines": 0, "total_text_lines": 0}
    event_types: dict = {}

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
            event_types[etype] = event_types.get(etype, 0) + 1

            if etype == "assistant":
                process_assistant_event(data, out, stats)
            elif etype == "result":
                process_result_event(data, out, stats)
            elif etype == "item.completed":
                process_item_completed_event(data, out, stats)

    pass  # evidence count is reported after assembly


def is_stream_valid(stream_file: str) -> bool:
    """Return True if stream is valid (no error event detected), False if an error result was found."""
    path = Path(stream_file)
    if not path.exists() or path.stat().st_size == 0:
        return True
    with open(stream_file) as f:
        for line in f:
            try:
                d = json.loads(line.strip())
                if d.get("type") == "result" and d.get("is_error"):
                    return False
            except json.JSONDecodeError:
                pass
    return True


def dump_debug_sample(stream_file: str, debug_stream: str, dimension_tag: str) -> None:
    """Save the stream file as a debug artifact and log a sample of it."""
    shutil.copy(stream_file, debug_stream)
    log_warning(f"No evidence extracted — debug stream saved to {Path(debug_stream).name}")

    with open(stream_file) as f:
        for line in f:
            try:
                d = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            if d.get("type") == "assistant":
                for block in d.get("message", {}).get("content", []):
                    if block.get("type") == "text":
                        text = block["text"]
                        preview = text[:400].replace("\n", "\n    ")
                        log_info(f"  debug sample ({len(text)} chars):\n    {preview}")
                        return

            if d.get("type") == "item.completed":
                item = d.get("item", {})
                if item.get("type") == "agent_message":
                    text = item.get("text", "")
                    if text:
                        preview = text[:400].replace("\n", "\n    ")
                        log_info(f"  debug sample ({len(text)} chars):\n    {preview}")
                        return

    log_info("  debug: no assistant text blocks found in stream")


# ---------------------------------------------------------------------------
# Phase runners
# ---------------------------------------------------------------------------

def run_analysis_phase(
    work_dir: str,
    dimension: str,
    prompt: str,
    stream_file: str,
    dimension_tag: str,
    analysis_budget: str | None = None,
    deep_unrestricted: bool = False,
) -> None:
    """Run the AI analysis phase, capturing stream-json output to stream_file."""
    cmd = get_ai_cmd()
    model = get_ai_model()
    analysis_tools = "Bash,Glob,Grep,Read"

    args = [cmd, "--print", "--output-format", "stream-json", "--verbose", "--tools", analysis_tools]
    if model:
        args.extend(["--model", model])
    if not deep_unrestricted and analysis_budget:
        args.extend(["--max-budget-usd", str(analysis_budget)])
    args.extend(["-p", prompt])

    env = os.environ.copy()
    if "CODEX_SANDBOX" not in env:
        env["CODEX_SANDBOX"] = "read-only"
    env.pop("CLAUDECODE", None)  # allow claude to run even when invoked from a Claude Code session

    stream_err_file = stream_file + ".err"
    heartbeat_interval = 60
    with open(stream_file, "w") as stream_out, open(stream_err_file, "w") as stream_err:
        process = subprocess.Popen(
            args,
            cwd=work_dir,
            env=env,
            stdout=stream_out,
            stderr=stream_err,
            stdin=subprocess.DEVNULL,
        )
        elapsed = 0
        while process.poll() is None:
            try:
                process.wait(timeout=heartbeat_interval)
            except subprocess.TimeoutExpired:
                elapsed += heartbeat_interval
                mins, secs = divmod(elapsed, 60)
                elapsed_label = f"{mins}m {secs}s" if mins else f"{secs}s"
                log_beat(f"{elapsed_label} elapsed")


def run_scoring_phase(
    work_dir: str,
    dimension: str,
    scoring_prompt: str,
    eval_file: str,
    dimension_tag: str,
    has_evidence: bool,
) -> bool:
    """Run the AI scoring phase, writing markdown output to eval_file.

    Returns True on success, False on failure.
    """
    from codecompass.evaluate.lib.common import log_step
    if has_evidence:
        log_step("Scoring")
    else:
        log_step("Scoring  (no evidence — scores will reflect this)")

    cmd = get_ai_cmd()
    model = get_ai_model()
    args = [cmd, "--print", "--tools", ""]
    if model:
        args.extend(["--model", model])
    args.extend(["-p", scoring_prompt])

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)  # allow claude to run even when invoked from a Claude Code session

    with open(eval_file, "w") as out:
        result = subprocess.run(
            args,
            cwd=work_dir,
            env=env,
            stdout=out,
            stderr=out,
            stdin=subprocess.DEVNULL,
        )

    eval_path = Path(eval_file)
    if result.returncode != 0 or not eval_path.exists() or eval_path.stat().st_size == 0:
        log_error(f"Scoring failed (exit code: {result.returncode})")
        return False

    log_success(eval_path.name)
    return True
