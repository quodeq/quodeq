"""Evaluation pipeline execution — config building and running.

Input resolution lives in ``_cli_resolution.py``; run lifecycle (directory
setup, RunLifecycleContext wiring, cleanup) lives in ``_cli_lifecycle.py``;
env/argv helpers in ``_cli_env.py``; suppression-aware score printing lives
in ``_cli_scoring.py``; run_evaluate's --diff-from resolution and post-run
consolidation/SARIF finalization live in ``_cli_evaluate_finalize.py``;
``_build_run_config``'s phase helpers live in ``_cli_run_config.py``. The
lifecycle helpers receive this module's patchable names as a
``LifecycleHooks`` bundle built here at call time (see ``_lifecycle_hooks``).

Patch targets — patch a name where the code that calls it looks it up, not
where it happens to be re-exported:

- Called from THIS module, so ``quodeq.cli_evaluation.<name>`` works:
  ``default_paths``, ``get_ai_model``, ``_subagent_model``, ``resolve_diff_files``,
  ``is_repo_url``, ``project_name_from_repo``, ``emit_marker``,
  ``cleanup_cloned_repo``, ``resolve_project_uuid`` and the ``evidence_rescore``
  pair.
- Read by ``_cli_run_config``: ``_env_int``, ``_no_verify``,
  ``_resolve_time_limit``, ``default_dispatch_policy``, ``expand_dimension_aliases``,
  ``AnalysisOptions``. Patch ``quodeq._cli_run_config.<name>``; patching them
  here is a silent no-op.
- ``_env_int``, ``_no_verify``, ``_subagent_model`` and the ``_ENV_*`` constants
  are re-exported below only because ``quodeq.cli`` imports them from here.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import NamedTuple

from quodeq.config.paths import default_paths
from quodeq.analysis.runner import RunConfig, run
from quodeq.analysis.scoring_pipeline import run_full
from quodeq.services.evidence_rescore import (  # noqa: F401 — facade patch targets
    rescore_dimension_from_evidence, score_dimension_from_evidence,
)
from quodeq.services.grade_formula import load_params
from quodeq.data.fs.project_resolver import resolve_project_uuid  # facade patch target
from quodeq.shared.logging import log_error, log_info, log_warning
from quodeq.shared.utils import get_ai_model, is_repo_url, project_name_from_repo, write_text  # is_repo_url/project_name_from_repo/get_ai_model are facade patch targets
from quodeq.data.fs.repo_handler import cleanup_cloned_repo  # facade patch target
from quodeq.analysis.runner_markers import emit_marker  # facade patch target
from quodeq.analysis.prereqs import check_evaluate_prereqs
from quodeq.analysis.diff_resolver import resolve_diff_files  # facade patch target
from quodeq.analysis.manifest_serialization import manifest_to_dict

# Re-export resolution / lifecycle / scoring helpers — keep the public API stable
from quodeq._cli_env import (  # noqa: F401 — _ENV_*/_env_int/_no_verify re-exported for quodeq.cli
    _ENV_MAX_DURATION, _ENV_MAX_TURNS, _ENV_NO_CONSOLIDATE, _ENV_POOL_BUDGET,
    _env_int, _environ, _no_verify, _subagent_model,
)
from quodeq._cli_run_config import (
    _build_analysis_options, _dimensions_filter, _resolve_limits,
)
from quodeq._cli_resolution import (  # noqa: F401
    ResolvedInputs, _build_manifest, _cleanup_worktree, _create_worktree,
    _override_manifest_single_file,
    _resolve_evaluation_inputs, _resolve_language, _resolve_repo,
    _resolve_scope, _resolve_single_file, filter_manifest_by_scope,
)
from quodeq import _cli_lifecycle
from quodeq._cli_lifecycle import (  # noqa: F401
    LifecycleHooks, _record_deadline_if_hit, _record_provider_fatal_if_cancelled,
)
from quodeq._cli_scoring import (  # noqa: F401
    _dim_evidence_counts, _format_adjusted_score, _print_scores,
)
from quodeq._cli_evaluate_finalize import (  # noqa: F401
    _apply_diff_from, _finalize_run_evaluate, _write_sarif_if_requested,
)

_logger = logging.getLogger(__name__)


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


class _RunConfigLocals(NamedTuple):
    """The per-run scalars `_build_run_config` resolves before assembling RunConfig.

    Named rather than a bare tuple so `_cli_run_config._build_analysis_options`
    reads them by attribute: reordering these fields can no longer silently
    swap, say, `consolidated` and `skip_scoring` at the call site.
    """
    consolidated: bool
    effective_ai_model: str | None
    subagent_model: str | None
    diff_from: str | None
    diff_files: set[str] | None
    skip_scoring: bool


def _resolve_run_config_locals(
    args: argparse.Namespace, inputs: ResolvedInputs, env: dict[str, str] | None,
) -> _RunConfigLocals:
    """Resolve the per-run scalars _build_run_config needs before assembling RunConfig."""
    _env = _environ(env)
    consolidated = not getattr(args, 'no_consolidated', False) and not bool(_env.get(_ENV_NO_CONSOLIDATE))
    if inputs.single_file:
        consolidated = False
        log_info("Single-file mode: per-dimension analysis for deeper coverage")

    ai_model = get_ai_model(env=env)
    subagent_model_val = _subagent_model(env=env)
    effective_ai_model = ai_model or subagent_model_val

    diff_from = getattr(args, "diff_from", None)
    diff_files: set[str] | None = getattr(args, "_diff_files", None)
    skip_scoring = diff_from is not None
    return _RunConfigLocals(
        consolidated=consolidated,
        effective_ai_model=effective_ai_model,
        subagent_model=subagent_model_val,
        diff_from=diff_from,
        diff_files=diff_files,
        skip_scoring=skip_scoring,
    )


def _build_run_config(args: argparse.Namespace, *, inputs: ResolvedInputs, evidence_dir: Path, run_dir: Path | None = None, env: dict[str, str] | None = None) -> RunConfig:
    """Assemble a RunConfig from CLI args and resolved inputs."""
    standards_dir = default_paths().standards_dir
    dimensions_filter = _dimensions_filter(args)
    resolved = _resolve_run_config_locals(args, inputs, env)
    limits = _resolve_limits(args, env)

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
        options=_build_analysis_options(dimensions_filter, resolved, limits),
        dispatch=limits.dispatch_policy,
    )


def _lifecycle_hooks() -> LifecycleHooks:
    """Bundle this module's globals for ``_cli_lifecycle``, resolved at call
    time so a patch on ``quodeq.cli_evaluation.<name>`` is what runs."""
    return LifecycleHooks(
        resolve_project_uuid=resolve_project_uuid,
        project_name_from_repo=project_name_from_repo,
        is_repo_url=is_repo_url,
        emit_marker=emit_marker,
        cleanup_cloned_repo=cleanup_cloned_repo,
        cleanup_worktree=_cleanup_worktree,
        get_ai_model=get_ai_model,
        save_manifest=_save_manifest,
        build_run_config=_build_run_config,
        execute_pipeline=_execute_pipeline,
    )


def _setup_run_dirs(args: argparse.Namespace, src: Path) -> tuple[Path, Path, Path]:
    """Resolve project UUID and create evidence/evaluation directories."""
    return _cli_lifecycle._setup_run_dirs(args, src, _lifecycle_hooks())


def _run_pipeline_with_cleanup(
    args: argparse.Namespace, inputs: ResolvedInputs, paths: tuple[Path, Path, Path],
) -> int:
    """Set up directories, build config, run the pipeline, and clean up cloned repos."""
    return _cli_lifecycle._run_pipeline_with_cleanup(args, inputs, paths, _lifecycle_hooks())


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

    diff_from_error = _apply_diff_from(args, inputs, resolve_diff_files)
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


_DIFF_EVAL_DEFAULT_TIME_LIMIT_S = 300  # CI diff review's own default; distinct from the CLI's DEFAULT_TIME_LIMIT


def run_diff_evaluation(
    src: str, *, base_ref: str, output_dir: Path,
    dimensions: str | None = None, time_limit: int = _DIFF_EVAL_DEFAULT_TIME_LIMIT_S,
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


# Public spellings of the names ``quodeq.cli`` re-exports. The underscore
# originals stay importable from here for in-package callers.
build_run_config = _build_run_config
execute_pipeline = _execute_pipeline
run_pipeline_with_cleanup = _run_pipeline_with_cleanup
save_manifest = _save_manifest
setup_run_dirs = _setup_run_dirs
