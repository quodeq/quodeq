"""Pool creation, launching, and stream-level evidence collection."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from quodeq.analysis._runner_markers import emit_marker
from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.subprocess import AnalysisConfig, count_files_from_stream
from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool
from quodeq.shared.constants import DEFAULT_TIME_LIMIT
from quodeq.shared.logging import log_info, log_warning
from quodeq.shared.utils import get_ai_cmd

_MAX_FILES_PER_AGENT = 30
_MAX_FILES_PER_AGENT_CAP = 50
# Auto-scale the IMPLICIT default time limit so large queues don't get
# killed mid-run: a fixed 600s budget chokes any dim with a queue larger
# than ~80 files (observed throughput ≈ 7-12 s/file with 8 agents) and
# the surviving pending files keep haunting the next run via the
# not_analyzed sweep. An EXPLICITLY chosen time_limit is a HARD CAP and
# is never scaled: the run stops dispatching at the cap, loaded agents
# drain, and the remainder carries over to the next run.
_SECONDS_PER_FILE_AUTOSCALE = 12
# Hard upper bound so a runaway queue can't lock up the run for days.
_MAX_AUTO_POOL_BUDGET = 7200  # 2 hours
# time_limit = 0 means "unlimited"; respect that and never scale it.
_UNLIMITED_BUDGET = 0


def _non_scout_providers(env: dict[str, str] | None = None) -> tuple[str, ...]:
    """Providers that skip scout mode (no per-token billing), read per call."""
    raw = (env if env is not None else os.environ).get(
        "QUODEQ_NON_SCOUT_PROVIDERS", "codex,gemini")
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def _resolve_time_limit(user_budget: int | None, queue_size: int) -> int:
    """Compute the effective time limit for a queue of *queue_size* files.

    An explicitly set `time_limit` is a HARD CAP and is returned verbatim
    (0 means "unlimited"): the user asked for that number, so the run
    dispatches until the cap and carries the remainder forward. Only when
    no limit was chosen (`None`) do we auto-scale the `DEFAULT_TIME_LIMIT`
    to give each file a fair slice of wallclock time, capped at
    `_MAX_AUTO_POOL_BUDGET`.
    """
    if user_budget is not None:
        return user_budget
    if queue_size <= 0:
        return DEFAULT_TIME_LIMIT
    needed = queue_size * _SECONDS_PER_FILE_AUTOSCALE
    return min(_MAX_AUTO_POOL_BUDGET, max(DEFAULT_TIME_LIMIT, needed))


def _extend_run_deadline(options: AnalysisOptions, time_limit: int) -> None:
    """Ratchet the run-level deadline forward to cover this pool's budget.

    AUTO-SCALED budgets only (the caller gates on time_limit=None): the
    granted pool budget can exceed a deadline pre-set by an outer caller;
    without this, the job watchdog SIGTERMs a healthy run at
    original-limit+grace while the pool believes it has hours left. Never
    call this with an explicit user budget — that budget is a run-wide
    hard cap, and re-extending it per dim launch defeats it. Never
    shortens the deadline, and leaves unlimited runs (no deadline) alone.
    Emits a marker so the job watchdog follows, and notifies the lifecycle
    (via the CLI-wired callback) so status.json and the dashboard
    countdown follow too.
    """
    if time_limit == _UNLIMITED_BUDGET or options.deadline_at is None:
        return
    new_deadline = time.monotonic() + time_limit
    if new_deadline <= options.deadline_at:
        return
    options.deadline_at = new_deadline
    new_iso = (
        datetime.now(timezone.utc) + timedelta(seconds=time_limit)
    ).isoformat()
    emit_marker("deadline_extended", deadline_at=new_iso, budget_s=time_limit)
    if options.on_deadline_extended is not None:
        try:
            options.on_deadline_extended(new_iso)
        except Exception as exc:  # noqa: BLE001 — a status write must not kill the launch
            log_warning(f"deadline extension notify failed: {exc}")


def _compute_files_per_agent(total_files: int) -> int:
    """Compute adaptive max files per agent. Capped to avoid turn limits."""
    return min(total_files, _MAX_FILES_PER_AGENT_CAP) if total_files > 0 else 0


def _default_subagent_model(env: dict[str, str] | None = None) -> str | None:
    """Return the subagent model override, or None to use the client's default.

    Checks SUBAGENT_MODEL first (set by dashboard/service layer),
    then QUODEQ_SUBAGENT_MODEL (direct env var override).
    """
    _env = env or os.environ
    return _env.get("SUBAGENT_MODEL") or _env.get("QUODEQ_SUBAGENT_MODEL") or None


@dataclass
class LaunchPoolParams:
    """Grouped parameters for launching a subagent pool."""
    evidence_dir: Path
    queue_path: Path
    prompt: str
    max_files_per_agent: int = _MAX_FILES_PER_AGENT
    all_files: list[str] | None = None


def _resolve_pool_budget(
    config: RunConfig, dim_id: str, params: LaunchPoolParams,
    env: dict[str, str] | None,
) -> int:
    """Resolve this pool's effective time limit and ratchet the run deadline.

    Must run BEFORE `_build_pool_config`: the pool snapshots deadline_at,
    and every deadline consumer (watchdog, drain checks, dashboard
    countdown) must agree on the granted budget, not the pre-scale one.
    Only the AUTO-SCALED budget may ratchet the deadline. An explicit
    time_limit is a run-wide HARD CAP: extending it here handed every
    dim's pool a fresh full budget, so a 1h run kept running for
    "1h after the LAST dim launch" (observed: run 838d807e).
    """
    queue_size = len(params.all_files) if params.all_files is not None else 0
    time_limit = _resolve_time_limit(config.options.time_limit, queue_size)
    base_user_budget = config.options.time_limit if config.options.time_limit is not None else DEFAULT_TIME_LIMIT
    if time_limit != base_user_budget and time_limit != _UNLIMITED_BUDGET:
        log_info(
            f"  [{dim_id}] Time limit auto-scaled: {base_user_budget}s → {time_limit}s"
            f" for {queue_size} files"
        )
    if config.options.time_limit is None:
        _extend_run_deadline(config.options, time_limit)
    return time_limit


def _build_pool_config(
    config: RunConfig, dim_id: str, params: LaunchPoolParams,
    time_limit: int, env: dict[str, str] | None,
) -> AnalysisConfig:
    """Build the per-launch AnalysisConfig for this pool."""
    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    subagent_model = config.options.subagent_model or _default_subagent_model(env) or config.options.ai_model
    return AnalysisConfig(
        analysis_budget=config.options.analysis_budget,
        compiled_dir=compiled_dir,
        max_turns=config.options.max_turns,
        max_duration=config.options.max_duration,
        ai_model=subagent_model,
        max_files_per_agent=params.max_files_per_agent,
        time_limit=time_limit,
        deadline_at=config.options.deadline_at,
        # Carry the RunConfig + dimension so the API runner can construct a
        # per-file cache writer (synchronous cache.put on file_done='ok').
        run_config=config,
        dimension=dim_id,
    )


def _launch_pool(
    config: RunConfig, dim_id: str, params: LaunchPoolParams,
    *, env: dict[str, str] | None = None,
) -> tuple[Any, list[Any]]:
    """Create and run a SubagentPool, returning its results."""
    time_limit = _resolve_pool_budget(config, dim_id, params, env)
    base_ac = _build_pool_config(config, dim_id, params, time_limit, env)
    n_agents = config.options.max_subagents

    # Skip scout mode for providers without per-token billing (e.g. Codex with
    # ChatGPT subscription).  Launch all agents immediately for faster results.
    ai_cmd = get_ai_cmd(env)
    use_scout = ai_cmd not in _non_scout_providers(env)

    pool = SubagentPool(
        paths=PoolPaths(work_dir=config.src, evidence_dir=params.evidence_dir, queue_path=params.queue_path,
                        src=config.src, all_files=params.all_files, standards_dir=config.standards_dir),
        options=PoolOptions(
            n_agents=n_agents,
            prompt=params.prompt,
            dimension=dim_id,
            scout_first=use_scout,
        ),
        config=base_ac,
    )
    return pool, pool.run()


def _collect_all_evidence(results: list[Any], cleanup_stream_fn: Any) -> int:
    """Sum files-read counts across all subagent result stream files, cleaning up each."""
    total = 0
    for r in results:
        if r.stream_file.exists():
            total += count_files_from_stream(r.stream_file)
            cleanup_stream_fn(r.stream_file)
    return total
