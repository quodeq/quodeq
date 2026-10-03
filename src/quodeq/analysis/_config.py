"""Analysis configuration dataclasses and type aliases."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from quodeq.analysis._drop_stats import DropStatsCounter
from quodeq.shared.constants import DEFAULT_TIME_LIMIT

if TYPE_CHECKING:
    from quodeq.analysis._command import CliMcpRegistry
    from quodeq.analysis.run_types import RunConfig

HeartbeatCallback = Callable[[int, dict], None]

_DEFAULT_MAX_FILES_PER_AGENT = 30

MCP_TOOL_REPORT_FINDING = "mcp__findings__report_finding"
MCP_TOOL_GET_NEXT_FILES = "mcp__findings__get_next_files"
MCP_TOOL_MARK_FILE_DONE = "mcp__findings__mark_file_done"


@dataclass(frozen=True)
class AnalysisConfig:
    """Configuration for an AI CLI analysis run."""
    jsonl_file: Path | None = None
    analysis_budget: str | None = None
    heartbeat_interval: int = 10
    heartbeat_callback: HeartbeatCallback | None = None
    ai_cmd: str | None = None
    ai_model: str | None = None
    # Binary override for the CLI spawn (AI_CMD_PATH); None spawns ``ai_cmd``.
    ai_cmd_path: str | None = None
    # Result-cache root the findings server writes under (``--cache-root``).
    # ``run_analysis`` fills it from the environment when the caller left it unset.
    cache_root: Path | None = None
    # None = no ceiling. The single-agent dimension step fills the run's
    # QUODEQ_DEFAULT_MAX_TURNS/DURATION ceilings; pool agents keep None.
    max_turns: int | None = None
    max_duration: int | None = None
    time_limit: int = DEFAULT_TIME_LIMIT
    deadline_at: float | None = None
    """Absolute monotonic-clock deadline for the whole run. None = unlimited."""
    run_deadline_at: float | None = None
    """The whole-run deadline when ``deadline_at`` is a per-dimension slice."""
    compiled_dir: Path | None = None
    dimension: str | None = None
    queue_path: Path | None = None
    agent_id: str = ""
    max_files_per_agent: int = _DEFAULT_MAX_FILES_PER_AGENT
    work_dir: Path | None = None
    context_size: int = 0
    # Optional ``RunConfig`` carrier so the API path can build a per-file
    # cache writer. ``None`` keeps legacy callers (no cache
    # writes) working. The import stays under TYPE_CHECKING (annotations are
    # lazy via ``from __future__ import annotations``) so ``run_types`` can
    # import this module at runtime without a cycle.
    run_config: RunConfig | None = None
    # The run's drop-stats accumulator and CLI-MCP registration cache,
    # carried directly rather than only through ``run_config`` so a builder
    # that must NOT set ``run_config`` (no per-file cache writer) can still
    # reach the run's owners. Every builder fills these from the same
    # ``RunConfig`` it would have passed as ``run_config``. ``None`` falls
    # back to ``run_config``'s owner, then the module-level default.
    drop_counter: DropStatsCounter | None = None
    mcp_registry: "CliMcpRegistry | None" = None


@dataclass(frozen=True)
class AgentParams:
    """Optional grouping of per-agent MCP config parameters."""
    queue_path: Path | None = None
    agent_id: str = ""
    work_dir: Path | None = None
    # Cache fingerprint inputs propagated to
    # ``findings_server.py`` so the subprocess writes cache entries with the
    # same keys as ``classify_files_via_cache``. ``None`` resolves to
    # ``"unknown"`` / ``""`` at emit time.
    model_id: str | None = None
    language: str | None = None
    # The standards ROOT, not compiled_dir: the subprocess's cache writer must key
    # under the same params_hash as ``build_cache_key_for_file``, which reads
    # ``RunConfig.standards_dir`` (parent of ``compiled/``) -- NOT
    # ``compiled_dir`` above, which is already the ``compiled/`` subdirectory.
    # Emitted as ``--standards-dir``. ``None`` when no ``RunConfig`` is
    # carried (no params fingerprint folded in).
    standards_dir: Path | None = None
    # Emitted as ``--cache-root``; None omits the flag (``run_analysis``
    # always resolves one before any spawn).
    cache_root: Path | None = None


@dataclass(frozen=True)
class SpawnPaths:
    """Paths for the AI CLI subprocess stdout/stderr capture files."""
    stream_file: Path
    stream_err: Path
