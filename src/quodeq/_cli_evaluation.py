"""Evaluation pipeline execution — config building and running.

Input resolution lives in ``_cli_resolution.py``; run lifecycle (directory
setup, RunLifecycleContext wiring, cleanup, SARIF export) lives in
``_cli_lifecycle.py``; suppression-aware score printing lives in
``_cli_scoring.py``; run_evaluate's --diff-from resolution and post-run
consolidation/SARIF finalization live in ``_cli_evaluate_finalize.py``. All
public names stay re-exported here (and, in turn, by ``quodeq.cli``) — ~15
test files patch ``quodeq._cli_evaluation.<name>``. A few re-exports below
have no direct caller left here (their callers moved out and reach them via
a deferred facade lookup on this module) but must stay importable as patch
targets.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from quodeq.config.paths import default_paths
from quodeq.analysis.dispatch_policy import default_dispatch_policy
from quodeq.analysis.runner import AnalysisOptions, RunConfig, run
from quodeq.analysis.scoring_pipeline import run_full
from quodeq.services.evidence_rescore import score_dimension_from_evidence  # noqa: F401 — facade patch target
from quodeq.services.grade_formula import load_params
from quodeq.data.fs.project_resolver import resolve_project_uuid  # noqa: F401 — facade patch target
from quodeq.shared.logging import log_error, log_info, log_warning
from quodeq.shared.utils import get_ai_model, is_repo_url, project_name_from_repo, write_text  # noqa: F401 — is_repo_url/project_name_from_repo/get_ai_model are facade patch targets
from quodeq.data.fs.repo_handler import cleanup_cloned_repo  # noqa: F401 — facade patch target
from quodeq.analysis._runner_markers import emit_marker  # noqa: F401 — facade patch target
from quodeq.analysis.prereqs import check_evaluate_prereqs
from quodeq.analysis._dimension_aliases import expand_dimension_aliases
from quodeq.analysis._diff_resolver import resolve_diff_files  # noqa: F401 — facade patch target
from quodeq.analysis.manifest_serialization import manifest_to_dict

# Re-export resolution / lifecycle / scoring helpers — keep the public API stable
from quodeq._cli_resolution import (  # noqa: F401
    ResolvedInputs, _build_manifest, _cleanup_worktree, _create_worktree,
    _filter_manifest_by_scope, _override_manifest_single_file,
    _resolve_evaluation_inputs, _resolve_language, _resolve_repo,
    _resolve_scope, _resolve_single_file,
)
from quodeq._cli_lifecycle import (  # noqa: F401
    _record_deadline_if_hit, _record_provider_fatal_if_cancelled,
    _run_pipeline_with_cleanup, _setup_run_dirs, _write_sarif_if_requested,
)
from quodeq._cli_scoring import (  # noqa: F401
    _count_excluded_findings, _dim_evidence_counts, _format_adjusted_score, _print_scores,
)
from quodeq._cli_evaluate_finalize import _apply_diff_from, _finalize_run_evaluate  # noqa: F401

_logger = logging.getLogger(__name__)

# Environment helpers
_ENV_MAX_TURNS = "QUODEQ_MAX_TURNS"
_ENV_MAX_DURATION = "QUODEQ_MAX_DURATION"
_ENV_POOL_BUDGET = "QUODEQ_POOL_BUDGET"
_ENV_TIME_LIMIT = "QUODEQ_TIME_LIMIT"


def _resolve_time_limit(args: argparse.Namespace, env: dict[str, str] | None = None) -> int | None:
    """Resolve the run-level time limit from CLI args or env.

    Precedence: explicit CLI flag > QUODEQ_TIME_LIMIT > legacy QUODEQ_POOL_BUDGET.
    Emits a one-line deprecation warning when the legacy CLI flag or env var is
    the source of the value.
    """
    src_env = env or os.environ
    if getattr(args, "pool_budget", None) is not None:
        # argparse stores both --time-limit and --pool-budget on the same dest;
        # detect deprecated form by scanning the original argv.
        if any(a == "--pool-budget" or a.startswith("--pool-budget=") for a in sys.argv[1:]):
            sys.stderr.write(
                "warning: --pool-budget is deprecated, use --time-limit instead\n"
            )
        return args.pool_budget
    if src_env.get(_ENV_TIME_LIMIT) is not None:
        return _env_int(_ENV_TIME_LIMIT, None, env=env)
    if src_env.get(_ENV_POOL_BUDGET) is not None:
        sys.stderr.write(
            f"warning: {_ENV_POOL_BUDGET} is deprecated, use {_ENV_TIME_LIMIT} instead\n"
        )
        return _env_int(_ENV_POOL_BUDGET, None, env=env)
    return None


def _env_int(var: str, default: int | None, env: dict[str, str] | None = None) -> int | None:
    """Read an environment variable as an int, returning *default* if unset or invalid."""
    raw = (env or os.environ).get(var)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _subagent_model(env: dict[str, str] | None = None) -> str | None:
    """Return the subagent model override from the environment, or None."""
    return (env or os.environ).get("SUBAGENT_MODEL") or None


def _no_verify(args: argparse.Namespace, env: dict[str, str] | None = None) -> bool:
    """Return True if verification should be skipped (CLI flag or env var)."""
    return args.no_verify or (env or os.environ).get("QUODEQ_NO_VERIFY") == "1"


# Pipeline execution
def _execute_pipeline(args: argparse.Namespace, config: RunConfig, evidence_dir: Path, evaluation_dir: Path) -> int:
    """Execute the evidence/scoring pipeline and print results.

    Three modes: scoring (default, run_full → scored evaluation/<dim>.json
    reports), --evidence-only (run() → merged <language>_evidence.json, no
    scoring), PR diff / skip_scoring (run() → per-dimension JSONL only, no
    merged json, no scoring).

    Domain errors (AnalysisError, EvaluationError) are intentionally *not*
    caught here — they propagate to _run_pipeline_with_cleanup so that
    RunLifecycleContext.__exit__ can write state=failed before the error is
    mapped to exit code 1.
    """
    if args.evidence_only or config.options.skip_scoring:
        label = "PR diff" if config.options.skip_scoring else "evidence collection"
        log_info(f"Starting {label} (this may take several minutes per dimension)...")
        evidence = run(config)
        if config.options.skip_scoring:
            # PR diff mode: per-dimension JSONL is already written by the pipeline.
            # No merged whole-repo artifact — PR reviews consume the JSONL directly.
            log_info(f"PR diff evaluation complete — evidence written to {evidence_dir}/")
        else:
            # --evidence-only: write the merged whole-repo Evidence JSON.
            out_file = evidence_dir / f"{config.language}_evidence.json"
            try:
                write_text(out_file, json.dumps(evidence.to_evidence_dict(), indent=2))
            except OSError as exc:
                log_error(f"Failed to write evidence file {out_file}: {exc}")
                return 1
            log_info(f"Evidence written to {out_file}")
        return 0

    log_info("Starting evaluation (this may take several minutes per dimension)...")
    scores = run_full(config, evaluation_dir, mode=args.mode)
    log_info(f"Report path: {evaluation_dir}/")
    log_info(f"Reports written to {evaluation_dir}/")
    run_dir = evaluation_dir.parent
    project_dir = run_dir.parent
    _print_scores(scores, run_dir, project_dir, load_params())
    return 0


def _save_manifest(manifest, evidence_dir: Path) -> None:
    """Save manifest for debugging (best-effort)."""
    if manifest and evidence_dir:
        try:
            write_text(evidence_dir / "manifest.json", json.dumps(manifest_to_dict(manifest), indent=2))
        except OSError as exc:
            _logger.debug("Could not write manifest: %s", exc)


def _resolve_run_config_locals(args: argparse.Namespace, inputs: ResolvedInputs, env: dict[str, str] | None):
    """Resolve the per-run scalars _build_run_config needs before assembling RunConfig."""
    _env = env or os.environ
    consolidated = not getattr(args, 'no_consolidated', False) and not bool(_env.get("QUODEQ_NO_CONSOLIDATE"))
    if inputs.single_file:
        consolidated = False
        log_info("Single-file mode: per-dimension analysis for deeper coverage")

    ai_model = get_ai_model(env=env)
    subagent_model_val = _subagent_model(env=env)
    effective_ai_model = ai_model or subagent_model_val

    diff_from = getattr(args, "diff_from", None)
    diff_files: set[str] | None = getattr(args, "_diff_files", None)
    skip_scoring = diff_from is not None
    return consolidated, effective_ai_model, subagent_model_val, diff_from, diff_files, skip_scoring


def _build_run_config(args: argparse.Namespace, *, inputs: ResolvedInputs, evidence_dir: Path, run_dir: Path | None = None, env: dict[str, str] | None = None) -> RunConfig:
    """Assemble a RunConfig from CLI args and resolved inputs."""
    standards_dir = default_paths().standards_dir
    expanded_dimensions = expand_dimension_aliases(args.dimensions)
    dimensions_filter = [d.strip() for d in expanded_dimensions.split(",") if d.strip()] if expanded_dimensions else None
    log_info(f"Dimensions: {', '.join(dimensions_filter)}" if dimensions_filter else "Dimensions: all")

    (
        consolidated, effective_ai_model, subagent_model_val,
        diff_from, diff_files, skip_scoring,
    ) = _resolve_run_config_locals(args, inputs, env)
    incremental_file_filter: set[str] | None = diff_files

    return RunConfig(
        src=inputs.src,
        language=inputs.language,
        standards_dir=standards_dir if standards_dir.exists() else None,
        work_dir=evidence_dir,
        run_dir=run_dir,
        manifest=inputs.manifest,
        dimensions_data=inputs.dims_data,
        evaluators_dir=default_paths().evaluators_dir,
        prompts_dir=default_paths().prompts_dir,
        options=AnalysisOptions(
            ai_model=effective_ai_model,
            dimensions=dimensions_filter,
            max_turns=args.max_turns if args.max_turns is not None else _env_int(_ENV_MAX_TURNS, None, env=env),
            max_duration=args.max_duration if args.max_duration is not None else _env_int(_ENV_MAX_DURATION, None, env=env),
            max_subagents=args.n_subagents,
            subagent_model=subagent_model_val,
            verify_findings=not _no_verify(args, env=env),
            consolidated=consolidated,
            time_limit=_resolve_time_limit(args, env=env),
            incremental=not (getattr(args, "clean_scan", False) or bool(getattr(args, "diff_from", None))),
            incremental_file_filter=incremental_file_filter,
            dry_run=getattr(args, "dry_run", False),
            diff_from=diff_from,
            skip_scoring=skip_scoring,
        ),
        dispatch=default_dispatch_policy(env=env or os.environ),
    )


def run_evaluate(args: argparse.Namespace) -> int:
    """Run the evaluation pipeline."""
    # --incremental is a deprecated no-op alias; incremental is already the default.
    if getattr(args, "legacy_incremental", False):
        log_warning(
            "--incremental is deprecated and will be removed in the next release. "
            "Incremental scans are now the default; use --clean-scan to force a "
            "full re-analysis."
        )

    if getattr(args, "clean_scan", False) and getattr(args, "diff_from", None):
        log_error(
            "Error: --clean-scan and --diff-from are mutually exclusive. "
            "--diff-from already produces evidence-only output for a specific "
            "ref; --clean-scan has no meaning in that mode."
        )
        return 1

    if not getattr(args, "dry_run", False):
        try:
            check_evaluate_prereqs()
        except RuntimeError as exc:
            log_error(f"Error: {exc}")
            return 1

    inputs = _resolve_evaluation_inputs(args)
    if inputs is None:
        return 1

    diff_from_error = _apply_diff_from(args, inputs)
    if diff_from_error is not None:
        return diff_from_error

    try:
        paths = _setup_run_dirs(args, inputs.src)
    except Exception:
        if inputs.worktree_dir and inputs.worktree_origin:
            _cleanup_worktree(inputs.worktree_origin, inputs.worktree_dir)
        raise
    result = _run_pipeline_with_cleanup(args, inputs, paths)
    _, _evidence_dir, evaluation_dir = paths
    return _finalize_run_evaluate(args, evaluation_dir, result)


def run_diff_evaluation(
    src: str, *, base_ref: str, output_dir: Path,
    dimensions: str | None = None, time_limit: int = 300,
) -> int:
    """Typed entry for CI review: evaluate *src* diffed against *base_ref*.

    The argv round-trip through the real parser stays inside the CLI package,
    so parser defaults remain single-sourced and callers (ci/) never
    fabricate presentation-layer input.
    """
    argv = ["evaluate", src, "--diff-from", base_ref, "--output", str(output_dir),
            "--time-limit", str(time_limit)]
    if dimensions:
        argv += ["--dimensions", dimensions]
    from quodeq.cli_parser import build_parser  # noqa: PLC0415
    return run_evaluate(build_parser().parse_args(argv))
