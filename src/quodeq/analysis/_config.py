"""Analysis configuration dataclasses and type aliases."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from quodeq.shared.constants import _DEFAULT_TIME_LIMIT

if TYPE_CHECKING:
    from quodeq.analysis._types import RunConfig

HeartbeatCallback = Callable[[int, dict], None]

_DEFAULT_MAX_FILES_PER_AGENT = 30

_DEFAULT_MAX_TURNS = int(os.environ.get("QUODEQ_DEFAULT_MAX_TURNS", "200"))
_DEFAULT_MAX_DURATION = int(os.environ.get("QUODEQ_DEFAULT_MAX_DURATION", "1800"))  # 30 minutes
_MCP_TOOL_REPORT_FINDING = "mcp__findings__report_finding"
_MCP_TOOL_GET_NEXT_FILES = "mcp__findings__get_next_files"


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
    time_limit: int = _DEFAULT_TIME_LIMIT
    deadline_at: float | None = None
    """Absolute monotonic-clock deadline for the whole run. None = unlimited."""
    compiled_dir: Path | None = None
    dimension: str | None = None
    queue_path: Path | None = None
    agent_id: str = ""
    max_files_per_agent: int = _DEFAULT_MAX_FILES_PER_AGENT
    work_dir: Path | None = None
    context_size: int = 0
    # Optional ``RunConfig`` carrier so the API path can build a per-file
    # cache writer (Task 3.5). Typed loosely to avoid a circular import:
    # ``_types`` imports from ``subprocess`` which re-exports ``HeartbeatCallback``
    # from this module. Stored as ``Any`` and read back as a ``RunConfig`` by
    # the API runner. ``None`` keeps legacy callers (no cache writes) working.
    run_config: Any = None


@dataclass(frozen=True)
class _AgentParams:
    """Optional grouping of per-agent MCP config parameters."""
    queue_path: Path | None = None
    agent_id: str = ""
    work_dir: Path | None = None


@dataclass(frozen=True)
class _SpawnPaths:
    """Paths for the AI CLI subprocess stdout/stderr capture files."""
    stream_file: Path
    stream_err: Path
