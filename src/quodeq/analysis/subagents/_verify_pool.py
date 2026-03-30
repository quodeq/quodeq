"""Verification pool launcher — extracted from runner.py to reduce file length."""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from quodeq.analysis.subprocess import AnalysisConfig
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool

if TYPE_CHECKING:
    from quodeq.analysis.runner import RunConfig

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
4. If the finding still applies, report it using the `report_finding` tool
   with the same fields (principle, type, severity, file, line, reason, snippet)
5. If the issue has been fixed or no longer applies, skip it silently

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
    queue_path = evidence_dir / f"{dim_id}_verify_queue.json"
    FileQueue(queue_path, files_to_verify, max_files_per_agent=_VERIFY_MAX_FILES_PER_AGENT)

    prompt = build_verify_prompt(manifest_path, dim_id)
    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    fast = _fast_model()

    ac = AnalysisConfig(
        compiled_dir=compiled_dir,
        max_turns=_VERIFY_MAX_TURNS,
        max_duration=_VERIFY_MAX_DURATION,
        ai_model=fast,
        dimension=dim_id,
    )

    n_agents = min(
        _VERIFY_N_AGENTS,
        (len(files_to_verify) + _VERIFY_MAX_FILES_PER_AGENT - 1) // _VERIFY_MAX_FILES_PER_AGENT,
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
