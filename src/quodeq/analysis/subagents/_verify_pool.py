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


def run_verification_pool(
    config: "RunConfig", dim_id: str, evidence_dir: Path,
    files_to_verify: list[str], manifest_path: Path,
) -> list[Any]:
    """Launch a fast verification pool to re-check previous findings.

    Uses the fast model (haiku by default) with a smaller pool.
    Confirmed findings are written to JSONL via MCP -> appear on dashboard.
    """
    from quodeq.analysis.subagents.verify import build_verify_prompt

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
