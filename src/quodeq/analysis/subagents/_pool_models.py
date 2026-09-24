"""Dataclasses and constants for the subagent pool."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quodeq.config.analysis_env import AGENT_FAILURE_STREAK_DEFAULT

AGENT_ID_PREFIX = "agent"
FUTURE_POLL_INTERVAL_S = 0.5
HEARTBEAT_JOIN_TIMEOUT_S = 2
SCOUT_TIMEOUT_S = 30              # 30s before forcing scale-up
DEFAULT_MAX_DURATION_S = 600      # 10 min per-agent ceiling; clamped lower by remaining run budget when set


@dataclass
class ScaleUpState:
    """Grouped parameters for scale-up decision logic."""
    pool_start: float
    max_duration: float
    scout_timeout: float
    scout_done: bool = False


@dataclass
class PoolPaths:
    """Grouped filesystem paths for the subagent pool."""
    work_dir: Path
    evidence_dir: Path
    queue_path: Path
    src: Path | None = None
    all_files: list[str] | None = None
    standards_dir: Path | None = None


@dataclass
class PoolOptions:
    """Grouped behavioral configuration for the subagent pool."""
    n_agents: int
    prompt: str
    dimension: str | list[str]
    scout_first: bool = True
    phase: str = "ANALYSIS"
    # The run's AnalysisOptions.agent_failure_streak_limit.
    agent_failure_streak_limit: int = AGENT_FAILURE_STREAK_DEFAULT


@dataclass
class SubagentResult:
    """Result from a single subagent run."""
    agent_id: str
    jsonl_file: Path
    stream_file: Path
    success: bool
    error: str = ""
