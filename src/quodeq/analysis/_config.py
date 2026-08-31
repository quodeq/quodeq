"""Analysis configuration dataclasses and type aliases."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from quodeq.config.analysis_env import default_max_duration, default_max_turns
from quodeq.shared.constants import DEFAULT_TIME_LIMIT

if TYPE_CHECKING:
    from quodeq.analysis._types import RunConfig

HeartbeatCallback = Callable[[int, dict], None]

_DEFAULT_MAX_FILES_PER_AGENT = 30

_MCP_TOOL_REPORT_FINDING = "mcp__findings__report_finding"
_MCP_TOOL_GET_NEXT_FILES = "mcp__findings__get_next_files"
_MCP_TOOL_MARK_FILE_DONE = "mcp__findings__mark_file_done"


@dataclass(frozen=True)
class AnalysisConfig:
    """Configuration for an AI CLI analysis run."""
    jsonl_file: Path | None = None
    analysis_budget: str | None = None
    heartbeat_interval: int = 10
    heartbeat_callback: HeartbeatCallback | None = None
    ai_cmd: str | None = None
    ai_model: str | None = None
    max_turns: int | None = field(default_factory=default_max_turns)
    max_duration: int | None = field(default_factory=default_max_duration)
    time_limit: int = DEFAULT_TIME_LIMIT
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
    # cache writer (Task 3.5). ``None`` keeps legacy callers (no cache
    # writes) working. The import stays under TYPE_CHECKING (annotations are
    # lazy via ``from __future__ import annotations``) so ``_types`` can
    # import this module at runtime without a cycle.
    run_config: RunConfig | None = None


@dataclass(frozen=True)
class _AgentParams:
    """Optional grouping of per-agent MCP config parameters."""
    queue_path: Path | None = None
    agent_id: str = ""
    work_dir: Path | None = None
    # Phase 1.5 (Task 3.5): cache fingerprint inputs propagated to
    # ``findings_server.py`` so the subprocess writes cache entries with the
    # same keys as ``classify_files_via_cache``. ``None`` resolves to
    # ``"unknown"`` / ``""`` at emit time.
    model_id: str | None = None
    language: str | None = None
    # Final-review fix (params-fingerprint cross-boundary bug): the standards
    # ROOT (``RunConfig.standards_dir``, parent of ``compiled/``) -- NOT
    # ``compiled_dir`` above, which is already the ``compiled/`` subdirectory.
    # Emitted as ``--standards-dir`` so the subprocess's cache writer keys
    # under the same params_hash as ``build_cache_key_for_file``. ``None``
    # when no ``RunConfig`` is carried (no params fingerprint folded in).
    standards_dir: Path | None = None


@dataclass(frozen=True)
class _SpawnPaths:
    """Paths for the AI CLI subprocess stdout/stderr capture files."""
    stream_file: Path
    stream_err: Path
