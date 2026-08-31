"""Logging-boundary ratchet: inner layers must not import a logging framework.

SEP-06: ``core/``, ``analysis/``, ``services/``, and ``config/`` accept an
injected ``quodeq.core.observability.LogSink`` instead of importing a logging
framework directly. A file that still imports ``logging`` (stdlib) or
``quodeq.shared.logging`` must be a DECLARED entry below with its reason.
The test fails when a new undeclared import appears (fix: accept a `log:
LogSink = NULL_LOG` param instead) and when a declared file no longer
imports logging (fix: delete the entry -- the list only shrinks).
"""
from __future__ import annotations

from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent.parent / "src" / "quodeq"

# Directories where inner-layer logging discipline applies (LAYER_RULES
# CROSS_CUTTING config/ is included -- it is not import-checked by
# check_imports.py, but the SEP-06 "no logging import" rule still applies).
_CHECKED_DIRS = ("core", "analysis", "services", "config")

# Relative to src/quodeq. Every entry still imports `logging` or
# `quodeq.shared.logging` -- either module-private, unrelated logging left
# untouched by the Group T sweep (the sweep covered only the per-site table
# in docs/superpowers/surveys/core-analysis.md §2), or a file the sweep
# added new sink-wiring to without removing its pre-existing logger. Burn
# down by giving the file's logging call sites a `log: LogSink = NULL_LOG`
# param and deleting the import.
DECLARED_LOGGING_SITES: dict[str, str] = {
    'analysis/_analysis_context.py': 'Analysis context - dimension loading and resolution - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/_api_runner.py': 'API runner for direct LLM evaluation - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/_command.py': 'AI CLI command-line construction and environment setup - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/_dimension_steps.py': 'Dimension step functions: prompt building, AI execution, evidence parsing - imports quodeq.shared.logging directly (out of scope for this sweep) and quodeq.shared.log_sink for quarantine-sink logging (log_malformed_jsonl_line/log_quarantined_findings) - plan-sanctioned composition wiring',
    'analysis/_drop_stats.py': 'Per-run aggregate of API-runner parse drops (issue #606) - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/_evidence_parser.py': 'Evidence-parsing composition wiring: imports quodeq.shared.log_sink for quarantine-sink logging (log_malformed_jsonl_line/log_quarantined_findings) - plan-sanctioned composition wiring, not a logging-boundary violation',
    'analysis/_pipeline.py': 'Pipeline coordination - dimension orchestration, merging, and public API - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/_process.py': 'Subprocess spawning, heartbeat monitoring, and error handling - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/_runner_markers.py': 'Structured marker emission and heartbeat callback for the runner pipeline - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/api_prompt_assembly.py': 'Prompt assembly for the direct API runner - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/cache/_failure_streak.py': 'Consecutive-failure circuit breaker for the dim runner - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/cache/cache_writer.py': 'Factory for the per-file cache-write callback passed to FindingsRouter - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/cache/consolidation.py': "Consolidation state - flip a completed run's cache entries - out of scope for this sweep (not a flagged per-site conversion)",
    'analysis/cache/dimension_helpers.py': 'Dimension-level cache helpers bridging RunConfig and the filesystem - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/cache/dimension_runner.py': 'V2 cache-aware dimension processor composing the B4 cache helpers - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/cache/gc.py': 'One-time garbage collection of cache entries from an older schema - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/cache/tiered.py': 'Tiered cache - local-first with optional remote fallback - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/checks/runner.py': "Run a dimension's deterministic checkers and fold the results into its evidence - out of scope for this sweep (not a flagged per-site conversion)",
    'analysis/manifest_build.py': 'Manifest building - walk a repository and produce a SourceManifest - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/mcp/provenance_gate.py': 'Deterministic provenance gate for the critical-severity bar (issue #639) - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/mcp/router.py': 'FindingsRouter: deduplicates and writes findings to JSONL - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/mcp/scope_gate.py': "Deterministic severity gate for a project's DECLARED threat model - out of scope for this sweep (not a flagged per-site conversion)",
    'analysis/prompts/_renderers.py': 'Template section renderers for analysis prompts - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/prompts/builder.py': 'Prompt builder - assembles per-dimension analysis prompts from compass.md template - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/run_lifecycle.py': "RunLifecycleContext - the run's lifecycle context manager - out of scope for this sweep (not a flagged per-site conversion)",
    'analysis/stream/parser.py': 'Stream-JSON event parser - extracts JSONL evidence lines from AI CLI output - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/stream/progress_reader.py': 'Incremental progress reader for AI analysis stream and JSONL files - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/subagents/_consolidated.py': 'Consolidated multi-dimension analysis - extracted from subagents/runner.py - imports quodeq.shared.log_sink for quarantine-sink logging (log_malformed_jsonl_line/log_quarantined_findings) - plan-sanctioned composition wiring',
    'analysis/subagents/_evidence_collector.py': 'Stream-level evidence collection for the subagent pool - imports quodeq.shared.log_sink for quarantine-sink logging (log_malformed_jsonl_line/log_quarantined_findings) - plan-sanctioned composition wiring, not a logging-boundary violation',
    'analysis/subagents/_heartbeat.py': 'Heartbeat and progress reporting for the subagent pool - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/subagents/_pool_launcher.py': 'Pool creation, launching, and stream-level evidence collection - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/subagents/_pool_scaling.py': 'Scaling logic: respawn decisions, scale-up computation, future collection - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/subagents/_pool_worker.py': 'Worker logic: building agent configs and running single subagents - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/subagents/_queue_state.py': 'Queue state persistence: atomic JSON read/write with file locking - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/subagents/_source_files.py': 'Source file listing and filtering for subagent queues - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/subagents/_verify_io.py': 'Finding verification I/O - evidence path resolution and JSONL parsing - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/subagents/jsonl_utils.py': 'JSONL merge and deduplication utilities for subagent pool output - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/subagents/pool.py': 'SubagentPool - launches N parallel AI CLI subprocesses sharing a FileQueue - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/subagents/verify.py': 'Prior-findings reader - used by priority scoring and the V2 cache layer - out of scope for this sweep (not a flagged per-site conversion)',
    'analysis/subprocess.py': 'AI analysis runner - dispatches to CLI subprocess or API runner - out of scope for this sweep (not a flagged per-site conversion)',
    'config/_asvs_network.py': 'Network fetch, retry, and integrity verification for ASVS downloads - out of scope for this sweep (not a flagged per-site conversion)',
    'config/_discipline_conf_loader.py': 'Load DisciplineRule instances from an INI-style .conf file - out of scope for this sweep (not a flagged per-site conversion)',
    'config/_discipline_detection.py': 'DisciplineRegistry: repo discipline detection with file-content matching - out of scope for this sweep (not a flagged per-site conversion)',
    'config/_env_loader.py': 'Load environment variables from .quodeq.env files - out of scope for this sweep (not a flagged per-site conversion)',
    'config/_fetch_client_class.py': 'Thread-safe HTTP fetcher with circuit breaker and retry - out of scope for this sweep (not a flagged per-site conversion)',
    'config/ai_provider.py': 'AI provider selection and configuration persistence - out of scope for this sweep (not a flagged per-site conversion)',
    'config/prompt_templates.py': 'Simple mustache-style template rendering for prompt files - out of scope for this sweep (not a flagged per-site conversion)',
    'core/standards/overrides.py': 'Per-project overrides for declared numeric requirement parameters - out of scope for this sweep (not a flagged per-site conversion)',
    'core/utils/io.py': 'Low-level text/JSON read helpers with centralized encoding - out of scope for this sweep (not a flagged per-site conversion)',
    'services/_cache.py': 'Shared LRU cache factory for dimension fetchers - out of scope for this sweep (not a flagged per-site conversion)',
    'services/_ephemeral_cleanup.py': 'Lifecycle management for ephemeral clones under ~/.quodeq/clones/ - out of scope for this sweep (not a flagged per-site conversion)',
    'services/_evaluations_index.py': 'Run/job index access - wraps JobManager + the SQLite run index - out of scope for this sweep (not a flagged per-site conversion)',
    'services/_external_jobs.py': 'Cancel path for external (CLI-started) evaluations - out of scope for this sweep (not a flagged per-site conversion)',
    'services/_fs_clone.py': 'Git clone helpers for the filesystem action provider - out of scope for this sweep (not a flagged per-site conversion)',
    'services/_fs_metadata.py': 'Metadata and detection helpers for the filesystem action provider - out of scope for this sweep (not a flagged per-site conversion)',
    'services/_fs_projects.py': 'Project CRUD helpers for the filesystem action provider - out of scope for this sweep (not a flagged per-site conversion)',
    'services/_fs_scan.py': 'Quick-scan service: extract project metadata without AI evaluation - out of scope for this sweep (not a flagged per-site conversion)',
    'services/_job_model.py': 'Job data model, store protocol, and in-memory store implementation - out of scope for this sweep (not a flagged per-site conversion)',
    'services/_post_run_hook.py': 'Post-run hook: runs after a JobManager job reaches a terminal state - out of scope for this sweep (not a flagged per-site conversion)',
    'services/_standards_io.py': 'I/O helpers and data-conversion utilities for the standards service - out of scope for this sweep (not a flagged per-site conversion)',
    'services/_standards_queries.py': 'Query operations for listing and retrieving standards - out of scope for this sweep (not a flagged per-site conversion)',
    'services/_trend_fetcher.py': 'Shared cache-backed, dismiss-adjusted SCALAR trend fetcher - out of scope for this sweep (not a flagged per-site conversion)',
    'services/_violations_jsonl.py': 'JSONL-specific parsing for extracting violations from MCP findings files - out of scope for this sweep (not a flagged per-site conversion)',
    'services/_violations_stream.py': 'Stream-specific parsing for extracting violations from live event log files - out of scope for this sweep (not a flagged per-site conversion)',
    'services/_warmup.py': 'Background warm-up of per-project score caches at server boot - out of scope for this sweep (not a flagged per-site conversion)',
    'services/deleted.py': 'Persistent storage for permanently-deleted findings - per-project JSON file - out of scope for this sweep (not a flagged per-site conversion)',
    'services/evidence_rescore.py': 'Rescore a dimension from its raw evidence, minus dismissed/deleted findings - imports the raw stdlib logger (out of scope for this sweep) and quodeq.shared.log_sink for quarantine-sink logging (log_malformed_jsonl_line/log_quarantined_findings) - plan-sanctioned composition wiring',
    'services/filesystem.py': 'FilesystemActionProvider - thin coordinator composing the provider collaborators - imports quodeq.shared.log_sink for SHARED_LOG, passed into composition-root wiring for register_project_with_rollback - plan-sanctioned composition wiring, not a logging-boundary violation',
    'services/grade_formula.py': 'User-tuned grade formula: apply/preview orchestration - out of scope for this sweep (not a flagged per-site conversion)',
    'services/mutation_rescore.py': 'Rescore-after-mutation helpers, shared by API routes and assistant actions - out of scope for this sweep (not a flagged per-site conversion)',
    'services/plugin_discovery.py': 'Discover available languages and return plugin metadata - out of scope for this sweep (not a flagged per-site conversion)',
    'services/score_run.py': 'Use case: score completed evidence after cancellation - imports the raw stdlib logger (out of scope for this sweep) and quodeq.shared.log_sink for quarantine-sink logging (log_malformed_jsonl_line/log_quarantined_findings) - plan-sanctioned composition wiring',
    'services/scoring/__init__.py': 'Scoring reader - single read-side entry point for all score data - out of scope for this sweep (not a flagged per-site conversion)',
    'services/scoring/_rescoring.py': 'Accumulated-rescore machinery for the scoring reader - out of scope for this sweep (not a flagged per-site conversion)',
    'services/shared_publish.py': 'Staging logic for publishing a project into the shared results repo - out of scope for this sweep (not a flagged per-site conversion)',
    'services/tooling_mixin.py': 'Mixin providing repo browsing and AI client discovery for the filesystem provider - out of scope for this sweep (not a flagged per-site conversion)',
    'services/violations.py': 'Violation resolution and aggregation for the filesystem action provider - out of scope for this sweep (not a flagged per-site conversion)',
}


def _imports_logging(text: str) -> bool:
    return (
        "import logging" in text
        or "from quodeq.shared.logging import" in text
        # quodeq.shared.log_sink transitively reaches shared.logging (its
        # SharedLog delegates to log_info/log_warning/log_debug/log_error),
        # so a file importing it is doing the same thing a raw logging
        # import would -- the needle must see it too.
        or "from quodeq.shared.log_sink import" in text
    )


def _files_importing_logging() -> set[str]:
    out: set[str] = set()
    for dirname in _CHECKED_DIRS:
        root = SRC_ROOT / dirname
        if not root.is_dir():
            continue
        for py in root.rglob("*.py"):
            rel = py.relative_to(SRC_ROOT).as_posix()
            try:
                text = py.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if _imports_logging(text):
                out.add(rel)
    return out


def test_no_undeclared_logging_imports_in_inner_layers():
    found = _files_importing_logging()
    undeclared = sorted(found - set(DECLARED_LOGGING_SITES))
    assert undeclared == [], (
        "logging imported directly in inner-layer file(s) outside "
        "core/observability.py's LogSink discipline. Accept an injected "
        "`log: LogSink = NULL_LOG` param instead (see "
        "quodeq.core.observability, quodeq.shared.log_sink), or (only for a "
        "genuinely out-of-scope site) add a declared entry with its "
        "reason:\n" + "\n".join(undeclared)
    )


def test_declared_logging_sites_are_not_stale():
    found = _files_importing_logging()
    stale = sorted(set(DECLARED_LOGGING_SITES) - found)
    assert stale == [], (
        "Declared logging sites no longer import logging -- delete their "
        "entries (the list only shrinks):\n" + "\n".join(stale)
    )
