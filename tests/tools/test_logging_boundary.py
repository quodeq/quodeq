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
# Most entries were left untouched by the Group T sweep for the same reason;
# only the per-file description differs, so the shared half is written once
# instead of pasted into every value.
_OUT_OF_SCOPE = " - out of scope for this sweep (not a flagged per-site conversion)"


def _out_of_scope(description: str) -> str:
    """*description* plus the shared "not a flagged per-site conversion" reason."""
    return description + _OUT_OF_SCOPE


DECLARED_LOGGING_SITES: dict[str, str] = {
    'analysis/_analysis_context.py': _out_of_scope('Analysis context - dimension loading and resolution'),
    'analysis/_api_batch.py': 'Per-dimension batch context and the sub-batch dispatch loop for the direct API runner - split out of subprocess.py, inherits its out-of-scope logging (not a flagged per-site conversion)',
    'analysis/_api_call.py': 'Direct LLM API call: request construction, the raw chat-completion round-trip, and error classification - split out of _api_runner.py, inherits its out-of-scope logging (not a flagged per-site conversion)',
    'analysis/_api_response.py': 'Completion response handling: finding parse, snippet repair re-ask, drop accounting - split out of _api_call.py, inherits its out-of-scope logging (not a flagged per-site conversion)',
    'analysis/_api_runner.py': _out_of_scope('API runner for direct LLM evaluation'),
    'analysis/_api_source_gathering.py': 'Credential loading and file-batching helpers for the direct API runner - split out of subprocess.py, inherits its out-of-scope logging (not a flagged per-site conversion)',
    'analysis/_api_standards_text.py': 'Source-file gathering and compiled-standards text for the API prompt - split out of subprocess.py, inherits its out-of-scope logging (not a flagged per-site conversion)',
    'analysis/_command.py': _out_of_scope('AI CLI command-line construction and environment setup'),
    'analysis/_dimension_steps.py': 'Dimension step functions: prompt building, AI execution, evidence parsing - imports quodeq.shared.logging directly (out of scope for this sweep); the quarantine-sink logging moved to evidence_parser.py with the parsing it belongs to',
    'analysis/_drop_stats.py': _out_of_scope('Per-run aggregate of API-runner parse drops (issue #606)'),
    'analysis/evidence_parser.py': 'Evidence-parsing composition wiring: imports quodeq.shared.log_sink for quarantine-sink logging (log_malformed_jsonl_line/log_quarantined_findings) - plan-sanctioned composition wiring, not a logging-boundary violation',
    'analysis/_pipeline.py': _out_of_scope('Pipeline coordination - dimension orchestration, merging, and public API'),
    'analysis/_process.py': _out_of_scope('Subprocess spawning, heartbeat monitoring, and error handling'),
    'analysis/runner_markers.py': _out_of_scope('Structured marker emission and heartbeat callback for the runner pipeline'),
    'analysis/api_prompt_assembly.py': _out_of_scope('Prompt assembly for the direct API runner'),
    'analysis/cache/_dimension_context.py': 'Pre-dispatch setup for the V2 cache-aware dimension processor (cache backend, trust model, file listing, classification) - split out of dimension_runner.py, inherits its out-of-scope logging (not a flagged per-site conversion)',
    'analysis/cache/failure_streak.py': _out_of_scope('Consecutive-failure circuit breaker for the dim runner'),
    'analysis/cache/_replay.py': "Cache-replay path: writing cached findings and their events.jsonl mirror back into a run's evidence - split out of dimension_runner.py, inherits its out-of-scope logging (not a flagged per-site conversion)",
    'analysis/cache/cache_writer.py': _out_of_scope('Factory for the per-file cache-write callback passed to FindingsRouter'),
    'analysis/cache/consolidation.py': _out_of_scope("Consolidation state - flip a completed run's cache entries"),
    'analysis/cache/dimension_helpers.py': _out_of_scope('Dimension-level cache helpers bridging RunConfig and the filesystem'),
    'analysis/cache/dimension_runner.py': _out_of_scope('V2 cache-aware dimension processor composing the B4 cache helpers'),
    'analysis/cache/tiered.py': _out_of_scope('Tiered cache - local-first with optional remote fallback'),
    'analysis/checks/runner.py': _out_of_scope("Run a dimension's deterministic checkers and fold the results into its evidence"),
    'analysis/manifest_build.py': _out_of_scope('Manifest building - walk a repository and produce a SourceManifest'),
    'analysis/mcp/provenance_gate.py': _out_of_scope('Deterministic provenance gate for the critical-severity bar (issue #639)'),
    'analysis/mcp/router.py': _out_of_scope('FindingsRouter: deduplicates and writes findings to JSONL'),
    'analysis/mcp/scope_gate.py': _out_of_scope("Deterministic severity gate for a project's DECLARED threat model"),
    'analysis/prompts/_renderers.py': _out_of_scope('Template section renderers for analysis prompts'),
    'analysis/prompts/builder.py': _out_of_scope('Prompt builder - assembles per-dimension analysis prompts from compass.md template'),
    'analysis/run_lifecycle.py': _out_of_scope("RunLifecycleContext - the run's lifecycle context manager"),
    'analysis/stream/parser.py': _out_of_scope('Stream-JSON event parser - extracts JSONL evidence lines from AI CLI output'),
    'analysis/stream/progress_reader.py': _out_of_scope('Incremental progress reader for AI analysis stream and JSONL files'),
    'analysis/subagents/_evidence_collector.py': 'Stream-level evidence collection for the subagent pool - imports quodeq.shared.log_sink for quarantine-sink logging (log_malformed_jsonl_line/log_quarantined_findings) - plan-sanctioned composition wiring, not a logging-boundary violation',
    'analysis/subagents/_heartbeat.py': _out_of_scope('Heartbeat and progress reporting for the subagent pool'),
    'analysis/subagents/_pool_launcher.py': _out_of_scope('Pool creation, launching, and stream-level evidence collection'),
    'analysis/subagents/_pool_scaling.py': _out_of_scope('Scaling logic: respawn decisions, scale-up computation, future collection'),
    'analysis/subagents/_pool_worker.py': _out_of_scope('Worker logic: building agent configs and running single subagents'),
    'analysis/subagents/_queue_state.py': _out_of_scope('Queue state persistence: atomic JSON read/write with file locking'),
    'analysis/subagents/_verify_io.py': _out_of_scope('Finding verification I/O - evidence path resolution and JSONL parsing'),
    'analysis/subagents/jsonl_utils.py': _out_of_scope('JSONL merge and deduplication utilities for subagent pool output'),
    'analysis/subagents/priority_config.py': 'Priority configuration loading - Task C6 (usability sweep) added a warning log for a previously-silent malformed/missing file_priority.json fallback; out of scope for the SEP-06 sweep (not a flagged per-site conversion)',
    'analysis/subagents/pool.py': _out_of_scope('SubagentPool - launches N parallel AI CLI subprocesses sharing a FileQueue'),
    'analysis/subagents/verify.py': _out_of_scope('Prior-findings reader - used by priority scoring and the V2 cache layer'),
    'analysis/subprocess.py': _out_of_scope('AI analysis runner - dispatches to CLI subprocess or API runner'),
    'config/_asvs_network.py': _out_of_scope('Network fetch, retry, and integrity verification for ASVS downloads'),
    'config/_discipline_conf_loader.py': _out_of_scope('Load DisciplineRule instances from an INI-style .conf file'),
    'config/_discipline_detection.py': _out_of_scope('DisciplineRegistry: repo discipline detection with file-content matching'),
    'config/_env_loader.py': _out_of_scope('Load environment variables from .quodeq.env files'),
    'config/_fetch_client_class.py': _out_of_scope('Thread-safe HTTP fetcher with circuit breaker and retry'),
    'config/ai_provider.py': _out_of_scope('AI provider selection and configuration persistence'),
    'config/prompt_templates.py': _out_of_scope('Simple mustache-style template rendering for prompt files'),
    'core/standards/overrides.py': _out_of_scope('Per-project overrides for declared numeric requirement parameters'),
    'core/utils/file_lock.py': "Platform file-locking helpers (fcntl/msvcrt dispatch) - moved inward from data/file_lock.py so api/ can use it per the check_imports layer rule, same as core/utils/io.py; its pre-existing 'import logging' was carried over unchanged, out of scope for this sweep",
    'core/utils/io.py': _out_of_scope('Low-level text/JSON read helpers with centralized encoding'),
    'services/cache.py': _out_of_scope('Shared LRU cache factory for dimension fetchers'),
    'services/ephemeral_cleanup.py': _out_of_scope('Lifecycle management for ephemeral clones under ~/.quodeq/clones/'),
    'services/_evaluations_index.py': _out_of_scope('Run/job index access - wraps JobManager + the SQLite run index'),
    'services/_external_jobs.py': _out_of_scope('Cancel path for external (CLI-started) evaluations'),
    'services/_fs_clone.py': _out_of_scope('Git clone helpers for the filesystem action provider'),
    'services/_fs_metadata.py': 'Metadata and detection helpers for the filesystem action provider - out of scope for this sweep (not a flagged per-site conversion); final-review fix wave (fault-tolerance cycle 1, item B) additionally imports quodeq.shared.log_sink for SHARED_LOG, threaded into cached_project_summary(log=...) so a best-effort score-cache write failure is no longer silently invisible - plan-sanctioned composition wiring, not a logging-boundary violation',
    'services/fs_project_helpers.py': 'Project-building helpers for the filesystem action provider - Task C6 (usability sweep) added a warning log for a previously-silent malformed-repo-identifier fallback in find_existing_project; out of scope for the SEP-06 sweep (not a flagged per-site conversion)',
    'services/fs_projects.py': _out_of_scope('Project CRUD helpers for the filesystem action provider'),
    'services/fs_scan.py': _out_of_scope('Quick-scan service: extract project metadata without AI evaluation'),
    'services/_job_model.py': _out_of_scope('Job data model, store protocol, and in-memory store implementation'),
    'services/_mutation_scoring.py': 'Slim rescore payload and default-run resolution for mutation deltas - Task C6 (usability sweep) added a warning log for a previously-silent list_runs failure in _resolve_default_run_id; out of scope for the SEP-06 sweep (not a flagged per-site conversion)',
    'services/_post_run_hook.py': _out_of_scope('Post-run hook: runs after a JobManager job reaches a terminal state'),
    'services/_standards_io.py': _out_of_scope('I/O helpers and data-conversion utilities for the standards service'),
    'services/_standards_queries.py': _out_of_scope('Query operations for listing and retrieving standards'),
    'services/trend_fetcher.py': 'Shared cache-backed, dismiss-adjusted SCALAR trend fetcher - out of scope for this sweep (not a flagged per-site conversion); final-review fix wave (fault-tolerance cycle 1, item B) additionally imports quodeq.shared.log_sink for SHARED_LOG, threaded into make_cache_backed_fetcher(log=...) so a best-effort score-cache write failure is no longer silently invisible - plan-sanctioned composition wiring, not a logging-boundary violation',
    'services/_violations_jsonl.py': _out_of_scope('JSONL-specific parsing for extracting violations from MCP findings files'),
    'services/_violations_stream.py': _out_of_scope('Stream-specific parsing for extracting violations from live event log files'),
    'services/warmup.py': _out_of_scope('Background warm-up of per-project score caches at server boot'),
    'services/deleted.py': _out_of_scope('Persistent storage for permanently-deleted findings - per-project JSON file'),
    'services/evidence_rescore.py': 'Rescore a dimension from its raw evidence, minus dismissed/deleted findings - imports the raw stdlib logger (out of scope for this sweep) and quodeq.shared.log_sink for quarantine-sink logging (log_malformed_jsonl_line/log_quarantined_findings) - plan-sanctioned composition wiring',
    'services/filesystem.py': 'FilesystemActionProvider - thin coordinator composing the provider collaborators - imports quodeq.shared.log_sink for SHARED_LOG, passed into composition-root wiring for register_project_with_rollback - plan-sanctioned composition wiring, not a logging-boundary violation',
    'services/grade_formula.py': _out_of_scope('User-tuned grade formula: apply/preview orchestration'),
    'services/mutation_rescore.py': _out_of_scope('Rescore-after-mutation helpers, shared by API routes and assistant actions'),
    'services/plugin_discovery.py': _out_of_scope('Discover available languages and return plugin metadata'),
    'services/score_run.py': 'Use case: score completed evidence after cancellation - imports the raw stdlib logger (out of scope for this sweep) and quodeq.shared.log_sink for quarantine-sink logging (log_malformed_jsonl_line/log_quarantined_findings) - plan-sanctioned composition wiring',
    'services/scoring/_rescoring.py': _out_of_scope('Accumulated-rescore machinery for the scoring reader'),
    'services/scoring/_scores_raw.py': _out_of_scope('Single-run scores: SQL-backed with a JSON-eval-file fallback - own logger (quodeq.services.scoring._scores_raw), no longer threaded from the package facade (M-MOD-3 import-cycle fix)'),
    'services/shared_publish.py': _out_of_scope('Staging logic for publishing a project into the shared results repo'),
    'services/tooling_mixin.py': _out_of_scope("AI-client and model discovery for the filesystem provider; also binds the inherited browse half's LogSink"),
    'services/violations.py': _out_of_scope('Violation resolution and aggregation for the filesystem action provider'),
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
