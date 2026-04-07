"""Verification pool launcher — extracted from runner.py to reduce file length."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from quodeq.analysis._types import RunConfig
from quodeq.analysis.subprocess import AnalysisConfig
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool

_VERIFY_MAX_FILES_PER_AGENT = 40
_VERIFY_MAX_TURNS = 100
_VERIFY_MAX_DURATION = 600
_VERIFY_N_AGENTS = 5
_DEFAULT_FAST_MODEL = "haiku"


def _fast_model(env: dict[str, str] | None = None) -> str:
    """Return the fast/verification model. Defaults to 'haiku'."""
    return (env or os.environ).get("QUODEQ_FAST_MODEL", _DEFAULT_FAST_MODEL)


_VERIFY_PROMPT_TEMPLATE = """\
You are re-verifying previous evaluation findings against the current codebase.
This is a quick verification pass — be fast and decisive.

## Task

For each file in the verification manifest at `{manifest_path}`:
1. Read the file from the queue
2. Look up its findings in the manifest
3. For each finding, check if the violation/compliance condition **still applies**
   to the current code — not just whether the line exists, but whether the
   underlying issue is still present. Each finding may include a `context` field
   with ~10 lines of surrounding code that can help assess whether the violation
   still applies
4. Before confirming, check for false positives:
   - A string/number literal inside a constant, enum, or config definition is
     NOT a "magic literal" violation — the definition IS the extraction
   - A long function that only registers routes/handlers with no extractable
     logic may not be meaningfully splittable
   - Duplicated code in test fixtures may be intentional for test clarity
   - If the finding targets the fix itself (the code IS the remediation), skip it
5. If the finding still applies after the false-positive check, report it using
   the `report_finding` tool with the same fields
6. If the issue has been fixed, no longer applies, or is a false positive, skip
   it silently

## Important

- Do NOT discover new findings — only verify existing ones
- Do NOT modify any files
- Read each file, check the findings, report confirmed ones, move on
- Be fast — this should take seconds per file

Dimension: {dimension}
"""


def build_verify_prompt(manifest_path: Path, dimension: str) -> str:
    """Build the prompt for verification subagents."""
    return _VERIFY_PROMPT_TEMPLATE.format(manifest_path=manifest_path, dimension=dimension)


def run_verification_pool(
    config: "RunConfig", dim_id: str, evidence_dir: Path,
    files_to_verify: list[str], manifest_path: Path,
) -> list[Any]:
    """Launch a fast verification pool to re-check previous findings.

    Uses the fast model (haiku by default) with a smaller pool.
    Confirmed findings are written to JSONL via MCP -> appear on dashboard.
    """
    prompt = build_verify_prompt(manifest_path, dim_id)
    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    fast = _fast_model()
    # For non-CLI providers (e.g. Ollama), treat verification the same as
    # analysis — no caps on agents or files-per-agent, no model swapping.
    is_local = False
    if config.options.ai_model and fast == _DEFAULT_FAST_MODEL:
        fast = config.options.ai_model
        is_local = True

    if is_local:
        # Local: use all configured agents, no file-count-based cap
        n_agents = config.options.max_subagents
    else:
        # Cloud/CLI: cap agents based on file count and max pool size
        n_agents = min(
            _VERIFY_N_AGENTS,
            config.options.max_subagents,
            (len(files_to_verify) + _VERIFY_MAX_FILES_PER_AGENT - 1) // _VERIFY_MAX_FILES_PER_AGENT,
        )

    queue_path = evidence_dir / f"{dim_id}_verify_queue.json"
    FileQueue(queue_path, files_to_verify, max_files_per_agent=_VERIFY_MAX_FILES_PER_AGENT)

    ac = AnalysisConfig(
        compiled_dir=compiled_dir,
        max_turns=_VERIFY_MAX_TURNS,
        max_duration=_VERIFY_MAX_DURATION,
        ai_model=fast,
        dimension=dim_id,
    )
    pool = SubagentPool(
        paths=PoolPaths(work_dir=config.src, evidence_dir=evidence_dir, queue_path=queue_path),
        options=PoolOptions(
            n_agents=n_agents,
            prompt=prompt,
            dimension=dim_id,
            scout_first=False,
        ),
        config=ac,
    )
    return pool.run()
