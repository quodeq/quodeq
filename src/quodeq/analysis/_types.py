"""Shared types for the analysis layer — extracted to break circular dependencies.

``RunConfig``, ``AnalysisOptions``, and ``_AnalysisContext`` are defined
here so that both ``runner.py`` and its helper modules (``_incremental``,
``_loops``, ``_backfill``, ``subagents/``) can import them without creating
mutual dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from quodeq.analysis._dimensions import DimensionsConfig
from quodeq.analysis.manifest import AnalysisTarget, SourceManifest
from quodeq.analysis.subprocess import HeartbeatCallback


@dataclass
class AnalysisOptions:
    """Optional runtime settings for an evaluation run."""
    analysis_budget: str | None = None
    heartbeat_callback: HeartbeatCallback | None = None
    template_path: Path | None = None
    dimensions: list[str] | None = None
    max_turns: int | None = None
    max_duration: int | None = None
    max_subagents: int = 1
    subagent_model: str | None = None
    ai_model: str | None = None
    verify_findings: bool = True
    consolidated: bool = True
    pool_budget: int | None = None
    deadline_at: float | None = None
    incremental: bool = False
    incremental_file_filter: set[str] | None = None
    dry_run: bool = False
    # PR diff mode: analyze only files changed since `diff_from`.
    # When set, skip_scoring is also set by the CLI layer so that fingerprint
    # persistence and scoring are suppressed — PR runs are evidence-only.
    diff_from: str | None = None
    skip_scoring: bool = False


@dataclass
class RunConfig:
    """Configuration for a single evaluation run."""
    src: Path
    language: str
    standards_dir: Path | None = None
    work_dir: Path | None = None
    options: AnalysisOptions = field(default_factory=AnalysisOptions)
    manifest: SourceManifest | None = None
    dimensions_data: DimensionsConfig | None = None
    target: AnalysisTarget | None = None
    evaluators_dir: Path | None = None

    @property
    def source_file_count(self) -> int:
        """Derive source file count from the target or manifest."""
        if self.target:
            return self.target.total_files
        return self.manifest.total_files if self.manifest else 0


@dataclass(frozen=True)
class _AnalysisContext:
    """Pre-loaded data reused across dimensions."""
    dimensions_data: DimensionsConfig
    date_str: str
    template: str
    subagent_template: str
    total: int
