"""Shared types for the analysis layer — extracted to break circular dependencies.

``RunConfig``, ``AnalysisOptions``, and ``_AnalysisContext`` are defined
here so that both ``runner.py`` and its helper modules (``_incremental``,
``_loops``, ``_backfill``, ``subagents/``) can import them without creating
mutual dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from quodeq.analysis._dimensions import DimensionsConfig
from quodeq.analysis.manifest import AnalysisTarget, SourceManifest
from quodeq.analysis.subprocess import HeartbeatCallback

if TYPE_CHECKING:
    from quodeq.analysis.cache.dimension_helpers import ClassifyResult


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
    time_limit: int | None = None
    deadline_at: float | None = None
    incremental: bool = True
    incremental_file_filter: set[str] | None = None
    dry_run: bool = False
    # PR diff mode: analyze only files changed since `diff_from`.
    # When set, skip_scoring is also set by the CLI layer so that fingerprint
    # persistence and scoring are suppressed — PR runs are evidence-only.
    diff_from: str | None = None
    skip_scoring: bool = False
    # Consecutive `file_done: error` markers that trip the dim-runner's
    # circuit breaker. 0 disables. The QUODEQ_FAILURE_STREAK env var,
    # when set, overrides this default at runtime.
    failure_streak_threshold: int = 5


@dataclass
class RunConfig:
    """Configuration for a single evaluation run.

    ``run_dir`` is the per-run directory (``<reports>/<project>/<run_id>/``)
    and is the canonical anchor for run-level metadata: ``status.json``,
    ``dimensions.json``, ``run.log``, etc. ``work_dir`` is the per-run
    *evidence* subdir (typically ``<run_dir>/evidence/``), where per-dim
    JSONLs and the dispatch-keys sidecar live. The two are distinct and
    must not be confused -- the lifecycle context writes to ``run_dir``
    while the dispatcher writes to ``work_dir``.
    """
    src: Path
    language: str
    standards_dir: Path | None = None
    work_dir: Path | None = None
    run_dir: Path | None = None
    options: AnalysisOptions = field(default_factory=AnalysisOptions)
    manifest: SourceManifest | None = None
    dimensions_data: DimensionsConfig | None = None
    target: AnalysisTarget | None = None
    evaluators_dir: Path | None = None
    # Per-run stash for ``classify_files_via_cache``. The pipeline classifies
    # files twice per dim (once upfront in ``_persist_dim_estimates`` for the
    # dashboard's totals, once inside the dim runner for actual dispatch).
    # When this is set to a dict, ``classify_files_via_cache`` populates it
    # on the first call for a given dim and short-circuits the second call
    # when the file list still matches. ``None`` means "stashing disabled" —
    # tests and one-shot callers that construct a fresh RunConfig get the
    # original behaviour without any wiring.
    _classify_cache: "dict[str, tuple[tuple[str, ...], ClassifyResult]] | None" = None

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
