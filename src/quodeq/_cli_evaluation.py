"""Evaluation pipeline execution — config building and running.

Input resolution helpers live in ``_cli_resolution.py``.
All public names are re-exported by ``quodeq.cli`` so that existing imports
(including tests) continue to work unchanged.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from quodeq.config.paths import default_paths
from quodeq.analysis.subprocess import AnalysisError
from quodeq.analysis.runner import AnalysisOptions, EvaluationError, RunConfig, run
from quodeq.engine.scoring_pipeline import run_full
from quodeq.shared.project_resolver import ProjectIdentity, resolve_project_uuid
from quodeq.shared.logging import log_error, log_info
from quodeq.shared.utils import get_ai_model, is_repo_url, project_name_from_repo, write_text
from quodeq.shared.repo_handler import cleanup_cloned_repo
from quodeq.engine._runner_markers import emit_marker
from quodeq.shared.prereqs import check_evaluate_prereqs
from quodeq.analysis._dimension_aliases import expand_dimension_aliases
from quodeq.shared.run_lifecycle import RunLifecycleContext

# Re-export resolution helpers — keep the public API stable
from quodeq._cli_resolution import (  # noqa: F401
    ResolvedInputs,
    _build_manifest,
    _cleanup_worktree,
    _create_worktree,
    _filter_manifest_by_scope,
    _override_manifest_single_file,
    _resolve_evaluation_inputs,
    _resolve_language,
    _resolve_repo,
    _resolve_scope,
    _resolve_single_file,
)

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

_ENV_MAX_TURNS = "QUODEQ_MAX_TURNS"
_ENV_MAX_DURATION = "QUODEQ_MAX_DURATION"
_ENV_POOL_BUDGET = "QUODEQ_POOL_BUDGET"


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


# ---------------------------------------------------------------------------
# Run directory setup
# ---------------------------------------------------------------------------

def _setup_run_dirs(args: argparse.Namespace, src: Path) -> tuple[Path, Path, Path]:
    """Resolve project UUID and create evidence/evaluation directories."""
    import uuid

    reports_root = Path(args.output)
    reports_root.mkdir(parents=True, exist_ok=True)

    project_name = project_name_from_repo(args.repo)
    location = "online" if is_repo_url(args.repo) else "local"
    scope = getattr(args, "scope", None)

    # Detect the git 'origin' remote so two clones of the same repo in
    # different local paths share a single project identity.
    remote_url = None
    if location == "local":
        from quodeq.shared._repo import git_remote_url
        remote_url = git_remote_url(str(src))

    project_uuid = resolve_project_uuid(
        reports_root,
        ProjectIdentity(project_name, str(src), None, location, scope_path=scope, remote_url=remote_url),
    )

    run_id = str(uuid.uuid4())
    evidence_dir = reports_root / project_uuid / run_id / "evidence"
    evaluation_dir = reports_root / project_uuid / run_id / "evaluation"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    return reports_root, evidence_dir, evaluation_dir


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

def _execute_pipeline(args: argparse.Namespace, config: RunConfig, evidence_dir: Path, evaluation_dir: Path) -> int:
    """Execute the evidence/scoring pipeline and print results.

    Domain errors (AnalysisError, EvaluationError) are intentionally *not*
    caught here — they propagate to _run_pipeline_with_cleanup so that
    RunLifecycleContext.__exit__ can write state=failed before the error is
    mapped to exit code 1.
    """
    if args.evidence_only:
        log_info("Starting evidence collection (this may take several minutes per dimension)...")
        evidence = run(config)
        out_file = evidence_dir / f"{config.language}_evidence.json"
        try:
            write_text(out_file, json.dumps(evidence.to_evidence_dict(), indent=2))
        except OSError as exc:
            log_error(f"Failed to write evidence file {out_file}: {exc}")
            return 1
        log_info(f"Evidence written to {out_file}")
    else:
        log_info("Starting evaluation (this may take several minutes per dimension)...")
        scores = run_full(config, evaluation_dir, mode=args.mode)
        log_info(f"Report path: {evaluation_dir}/")
        log_info(f"Reports written to {evaluation_dir}/")
        for dim, score in scores.items():
            print(f"  {dim}: {score}")
    return 0


def _save_manifest(manifest, evidence_dir: Path) -> None:
    """Save manifest for debugging (best-effort)."""
    if manifest and evidence_dir:
        try:
            write_text(evidence_dir / "manifest.json", json.dumps(manifest.to_dict(), indent=2))
        except OSError as exc:
            _logger.debug("Could not write manifest: %s", exc)


def _build_run_config(args: argparse.Namespace, *, inputs: ResolvedInputs, evidence_dir: Path, env: dict[str, str] | None = None) -> RunConfig:
    """Assemble a RunConfig from CLI args and resolved inputs."""
    _env = env or os.environ
    standards_dir = default_paths().standards_dir
    expanded_dimensions = expand_dimension_aliases(args.dimensions)
    dimensions_filter = [d.strip() for d in expanded_dimensions.split(",") if d.strip()] if expanded_dimensions else None
    log_info(f"Dimensions: {', '.join(dimensions_filter)}" if dimensions_filter else "Dimensions: all")

    is_single_file = getattr(args, '_single_file', False)

    consolidated = not getattr(args, 'no_consolidated', False) and not bool(_env.get("QUODEQ_NO_CONSOLIDATE"))
    if is_single_file:
        consolidated = False
        log_info("Single-file mode: per-dimension analysis for deeper coverage")

    ai_model = get_ai_model(env=env)
    subagent_model_val = _subagent_model(env=env)
    effective_ai_model = ai_model or subagent_model_val

    return RunConfig(
        src=inputs.src,
        language=inputs.language,
        standards_dir=standards_dir if standards_dir.exists() else None,
        work_dir=evidence_dir,
        manifest=inputs.manifest,
        dimensions_data=inputs.dims_data,
        evaluators_dir=default_paths().evaluators_dir,
        options=AnalysisOptions(
            ai_model=effective_ai_model,
            dimensions=dimensions_filter,
            max_turns=args.max_turns if args.max_turns is not None else _env_int(_ENV_MAX_TURNS, None, env=env),
            max_duration=args.max_duration if args.max_duration is not None else _env_int(_ENV_MAX_DURATION, None, env=env),
            max_subagents=args.n_subagents,
            subagent_model=subagent_model_val,
            verify_findings=not _no_verify(args, env=env),
            consolidated=consolidated,
            pool_budget=args.pool_budget if args.pool_budget is not None else _env_int(_ENV_POOL_BUDGET, None, env=env),
            incremental=args.incremental,
            dry_run=getattr(args, "dry_run", False),
        ),
    )


def _run_pipeline_with_cleanup(
    args: argparse.Namespace, inputs: ResolvedInputs, paths: tuple[Path, Path, Path],
) -> int:
    """Set up directories, build config, run the pipeline, and clean up cloned repos."""
    _reports_root, evidence_dir, evaluation_dir = paths
    log_info(f"Report path: {evaluation_dir}")
    run_dir = evaluation_dir.parent
    run_id = run_dir.name
    project_uuid = run_dir.parent.name
    emit_marker("report_path", project=project_uuid, runId=run_id)
    _save_manifest(inputs.manifest, evidence_dir)

    # Write a .pid file so the dashboard can detect and cancel this external run
    pid_file = run_dir / ".pid"
    try:
        pid_file.write_text(str(os.getpid()))
    except OSError:
        pass  # non-fatal; cancel-by-filesystem just won't work for this run

    config = _build_run_config(args, inputs=inputs, evidence_dir=evidence_dir)

    # Install a per-run log handler so every log_info lands in run.log.
    from quodeq.shared.run_log import RunLogHandler, RunLogWriter
    writer = RunLogWriter(run_dir)
    handler = RunLogHandler(writer)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger_root = logging.getLogger("quodeq")
    _logger_root.addHandler(handler)

    # Resolve dimensions list for status.json metadata.
    # Defensively coerce to a real list — config may be a Mock in tests.
    _raw_dims = getattr(getattr(config, "options", None), "dimensions", None)
    dimensions_list: list[str] = list(_raw_dims) if isinstance(_raw_dims, list) else []

    try:
        # Lifecycle context: pending → running on enter, done on clean exit,
        # failed on exception, cancelled on SIGINT/SIGTERM/SIGHUP or atexit.
        try:
            with RunLifecycleContext(
                run_dir=run_dir,
                job_id=f"ext-{run_id}",
                dimensions=dimensions_list,
            ) as lifecycle:
                try:
                    result = _execute_pipeline(args, config, evidence_dir, evaluation_dir)
                    lifecycle.transition_to_finalizing()
                    return result
                finally:
                    # Clean up .pid file on exit so we don't leave stale PIDs
                    try:
                        pid_file.unlink(missing_ok=True)
                    except OSError:
                        pass
                    if is_repo_url(args.repo):
                        cleanup_cloned_repo(str(inputs.src))
                    worktree_dir = getattr(args, "_worktree_dir", None)
                    worktree_origin = getattr(args, "_worktree_origin", None)
                    if worktree_dir and worktree_origin:
                        _cleanup_worktree(worktree_origin, worktree_dir)
        except (AnalysisError, EvaluationError) as exc:
            # RunLifecycleContext.__exit__ has already written state=failed.
            # Map the domain error to exit code 1.
            log_error(f"{exc}")
            return 1
    finally:
        _logger_root.removeHandler(handler)
        writer.close()


def run_evaluate(args: argparse.Namespace) -> int:
    """Run the evaluation pipeline."""
    if getattr(args, "incremental", False) and getattr(args, "diff_from", None):
        log_error(
            "Error: --incremental and --diff-from are mutually exclusive. "
            "--incremental is for nightly whole-repo runs; --diff-from is for "
            "PR-scoped analysis."
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

    try:
        paths = _setup_run_dirs(args, inputs.src)
    except Exception:
        worktree_dir = getattr(args, "_worktree_dir", None)
        worktree_origin = getattr(args, "_worktree_origin", None)
        if worktree_dir and worktree_origin:
            _cleanup_worktree(worktree_origin, worktree_dir)
        raise
    return _run_pipeline_with_cleanup(args, inputs, paths)
