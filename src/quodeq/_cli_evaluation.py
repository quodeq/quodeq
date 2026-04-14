"""Evaluation pipeline helpers extracted from cli.py to keep it under 300 lines.

All public names are re-exported by ``quodeq.cli`` so that existing imports
(including tests) continue to work unchanged.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile as _tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from quodeq.config.paths import default_paths
from quodeq.analysis.subprocess import AnalysisError
from quodeq.analysis.runner import AnalysisOptions, EvaluationError, RunConfig, run
from quodeq.engine.scoring_pipeline import run_full
from quodeq.shared.project_resolver import ProjectIdentity, resolve_project_uuid
from quodeq.shared.repo_handler import cleanup_cloned_repo, prepare_repository
from quodeq.shared.utils import get_ai_model, is_repo_url, project_name_from_repo, read_json, write_text
from quodeq.shared.validation import validate_path_segment
from quodeq.analysis.manifest import SourceManifest, build_manifest, detect_language
from quodeq.analysis.manifest_models import AnalysisTarget
from quodeq.analysis.runner import load_universal_dimensions
from quodeq.engine._runner_markers import emit_marker
from quodeq.shared.prereqs import check_evaluate_prereqs

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ResolvedInputs:
    """Grouped evaluation inputs that always travel together."""
    src: Path
    language: str
    manifest: object  # SourceManifest | None
    dims_data: dict


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
# Worktree management
# ---------------------------------------------------------------------------

def _create_worktree(repo_dir: Path, branch: str) -> Path | None:
    """Create a temporary git worktree for the given branch.

    Returns the worktree path, or None on failure.
    """
    worktree_dir = Path(_tempfile.mkdtemp(prefix=f"quodeq-wt-{branch.replace('/', '-')}-"))
    try:
        subprocess.run(
            ["git", "-C", str(repo_dir), "worktree", "add", str(worktree_dir), branch],
            capture_output=True, text=True, check=True, timeout=30,
        )
        return worktree_dir
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"Failed to create worktree for branch '{branch}': {exc}", file=sys.stderr)
        try:
            worktree_dir.rmdir()
        except OSError:
            pass
        return None


def _cleanup_worktree(repo_dir: Path, worktree_dir: Path) -> None:
    """Remove a temporary git worktree."""
    try:
        subprocess.run(
            ["git", "-C", str(repo_dir), "worktree", "remove", str(worktree_dir), "--force"],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        _logger.debug("Failed to clean up worktree %s: %s", worktree_dir, exc)


# ---------------------------------------------------------------------------
# Repo / language / manifest resolution
# ---------------------------------------------------------------------------

def _resolve_repo(args: argparse.Namespace) -> Path | None:
    """Resolve the repo argument to a local path (cloning if needed)."""
    repo_path = args.repo
    try:
        is_remote = is_repo_url(repo_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return None
    if is_remote:
        try:
            repo_path = prepare_repository(repo_path)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as exc:
            print(f"Failed to clone repository: {exc}", file=sys.stderr)
            return None
    src = Path(repo_path).resolve()
    if not src.exists():
        print(f"Repository path does not exist: {src}. Verify the path is correct and accessible.", file=sys.stderr)
        return None

    branch = getattr(args, "branch", None)
    if branch and not is_remote and src.is_dir():
        worktree = _create_worktree(src, branch)
        if worktree is None:
            return None
        args._worktree_origin = src
        args._worktree_dir = worktree
        src = worktree

    return src


def _setup_run_dirs(args: argparse.Namespace, src: Path) -> tuple[Path, Path, Path]:
    """Resolve project UUID and create evidence/evaluation directories."""
    reports_root = Path(args.output)
    reports_root.mkdir(parents=True, exist_ok=True)

    project_name = project_name_from_repo(args.repo)
    location = "online" if is_repo_url(args.repo) else "local"
    scope = getattr(args, "scope", None)
    project_uuid = resolve_project_uuid(reports_root, ProjectIdentity(project_name, str(src), None, location, scope_path=scope))

    run_id = str(uuid.uuid4())
    evidence_dir = reports_root / project_uuid / run_id / "evidence"
    evaluation_dir = reports_root / project_uuid / run_id / "evaluation"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    return reports_root, evidence_dir, evaluation_dir


def _resolve_language(args: argparse.Namespace, src: Path, paths) -> str | None:
    """Detect or validate the language for a repo using universal detection."""
    if args.language:
        validate_path_segment(args.language)
        return args.language
    if not paths.detection_file.exists():
        return None
    try:
        return detect_language(src, paths.detection_file)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return None


def _build_manifest(
    args: argparse.Namespace, src: Path, paths,
    scope_path: str | None = None,
) -> "SourceManifest | None":
    """Build a source manifest for the repository."""
    if args.no_prescan:
        return None

    detection_file = paths.detection_file
    if not detection_file.exists():
        return None

    detection = read_json(detection_file)
    disciplines_conf = paths.disciplines_conf if paths.disciplines_conf.exists() else None
    manifest = build_manifest(src, detection, disciplines_conf, scope_path=scope_path)
    if manifest.targets:
        langs = ", ".join(
            f"{t.language} ({t.total_files})"
            for t in manifest.targets
        )
        print(f"Detected: {langs}", file=sys.stderr)
    print(f"Source files: {manifest.total_files}", file=sys.stderr)
    return manifest


# ---------------------------------------------------------------------------
# _resolve_evaluation_inputs — broken into sub-helpers
# ---------------------------------------------------------------------------

def _resolve_scope(src: Path, args: argparse.Namespace) -> tuple[str | None, bool]:
    """Resolve --scope flag against the source directory.

    Returns ``(scope_path, ok)`` where *ok* is False when validation fails
    (error already printed to stderr).
    """
    scope = getattr(args, "scope", None)
    if not scope or not src.is_dir():
        return None, True
    scoped = (src / scope).resolve()
    if not scoped.exists():
        print(f"Scope path does not exist: {scoped}", file=sys.stderr)
        return None, False
    if not scoped.is_relative_to(src):
        print(f"Scope must be within the repository: {scope}", file=sys.stderr)
        return None, False
    kind = "file" if scoped.is_file() else "folder"
    print(f"Scoped evaluation: {scope} ({kind}, repo root: {src})", file=sys.stderr)
    return scope, True


def _resolve_single_file(src: Path) -> tuple[Path, str | None]:
    """Detect single-file mode and return (project_root, relative_path | None)."""
    if not src.is_file():
        return src, None
    file_path = src
    project_root = file_path.parent
    candidate = file_path.parent
    while candidate != candidate.parent:
        if (candidate / ".git").exists():
            project_root = candidate
            break
        candidate = candidate.parent
    single_file = str(file_path.relative_to(project_root))
    print(f"Single-file evaluation: {single_file} (project root: {project_root})", file=sys.stderr)
    return project_root, single_file


def _filter_manifest_by_scope(
    manifest: "SourceManifest | None", scope_path: str,
) -> "SourceManifest | None":
    """Narrow a manifest to only files under *scope_path*.

    Returns None (with error printed) when no files match.
    """
    if not manifest or not manifest.targets:
        return manifest

    prefix = scope_path.rstrip("/") + "/"
    scoped_targets: list[AnalysisTarget] = []
    total = 0
    all_stats: dict[str, int] = {}

    for t in manifest.targets:
        scoped_files = [f for f in t.source_files if f.startswith(prefix) or f == scope_path]
        if not scoped_files:
            continue
        stats: dict[str, int] = {}
        for f in scoped_files:
            ext = os.path.splitext(f)[1]
            if ext:
                stats[ext] = stats.get(ext, 0) + 1
        scoped_targets.append(AnalysisTarget(
            name=t.name, language=t.language,
            source_files=scoped_files, total_files=len(scoped_files),
            language_stats=stats, category=t.category,
        ))
        total += len(scoped_files)
        for k, v in stats.items():
            all_stats[k] = all_stats.get(k, 0) + v

    if scoped_targets:
        print(f"Scope filter: {total} files under '{scope_path}'", file=sys.stderr)
        return SourceManifest(targets=scoped_targets, total_files=total, language_stats=all_stats)

    print(f"No source files found under scope '{scope_path}'", file=sys.stderr)
    print("The scoped folder contains no recognized source code files.", file=sys.stderr)
    return None


def _override_manifest_single_file(
    language: str, single_file: str, args: argparse.Namespace,
) -> SourceManifest:
    """Create a single-file manifest and flag args for single-file mode."""
    ext = os.path.splitext(single_file)[1]
    target = AnalysisTarget(
        name=single_file, language=language,
        source_files=[single_file], total_files=1,
        language_stats={ext: 1} if ext else {},
    )
    args._single_file = True
    return SourceManifest(targets=[target], total_files=1, language_stats={ext: 1} if ext else {})


def _resolve_evaluation_inputs(args: argparse.Namespace) -> ResolvedInputs | None:
    """Resolve src, language, manifest, and dims_data from CLI args.

    Returns ``None`` (with error printed to stderr) if any step fails.
    """
    src = _resolve_repo(args)
    if src is None:
        return None

    scope_path, ok = _resolve_scope(src, args)
    if not ok:
        return None

    src, single_file = _resolve_single_file(src)

    paths = default_paths()
    if not paths.detection_file.exists() or not paths.dimensions_file.exists():
        print(
            "Configuration not found: detection.json and dimensions.json are required. "
            "These files are created automatically when you install Quodeq standards. "
            f"Expected location: {paths.detection_file.parent}",
            file=sys.stderr,
        )
        return None

    language = _resolve_language(args, src, paths)
    if language is None:
        return None

    try:
        dims_data = load_universal_dimensions(paths.dimensions_file)
    except ValueError as exc:
        print(f"Invalid dimensions config: {exc}", file=sys.stderr)
        return None

    manifest = _build_manifest(args, src, paths, scope_path=scope_path)

    if scope_path and manifest:
        manifest = _filter_manifest_by_scope(manifest, scope_path)
        if manifest is None:
            return None

    if single_file:
        manifest = _override_manifest_single_file(language, single_file, args)

    return ResolvedInputs(src=src, language=language, manifest=manifest, dims_data=dims_data)


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

def _execute_pipeline(args: argparse.Namespace, config: RunConfig, evidence_dir: Path, evaluation_dir: Path) -> int:
    """Execute the evidence/scoring pipeline and print results."""
    try:
        if args.evidence_only:
            print("Starting evidence collection (this may take several minutes per dimension)...", file=sys.stderr)
            evidence = run(config)
            out_file = evidence_dir / f"{config.language}_evidence.json"
            try:
                write_text(out_file, json.dumps(evidence.to_evidence_dict(), indent=2))
            except OSError as exc:
                print(f"Failed to write evidence file {out_file}: {exc}", file=sys.stderr)
                return 1
            print(f"Evidence written to {out_file}", file=sys.stderr)
        else:
            print("Starting evaluation (this may take several minutes per dimension)...", file=sys.stderr)
            scores = run_full(config, evaluation_dir, mode=args.mode)
            print(f"Report path: {evaluation_dir}/", file=sys.stderr)
            print(f"Reports written to {evaluation_dir}/", file=sys.stderr)
            for dim, score in scores.items():
                print(f"  {dim}: {score}")
    except (AnalysisError, EvaluationError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1
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
    dimensions_filter = [d.strip() for d in args.dimensions.split(",") if d.strip()] if args.dimensions else None
    print(f"Dimensions: {', '.join(dimensions_filter)}" if dimensions_filter else "Dimensions: all", file=sys.stderr)

    is_single_file = getattr(args, '_single_file', False)

    consolidated = not getattr(args, 'no_consolidated', False) and not bool(_env.get("QUODEQ_NO_CONSOLIDATE"))
    if is_single_file:
        consolidated = False
        print("Single-file mode: per-dimension analysis for deeper coverage", file=sys.stderr)

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
        ),
    )


def _run_pipeline_with_cleanup(
    args: argparse.Namespace, inputs: ResolvedInputs, paths: tuple[Path, Path, Path],
) -> int:
    """Set up directories, build config, run the pipeline, and clean up cloned repos."""
    _reports_root, evidence_dir, evaluation_dir = paths
    print(f"Report path: {evaluation_dir}", file=sys.stderr)
    run_id = evaluation_dir.parent.name
    project_uuid = evaluation_dir.parent.parent.name
    emit_marker("report_path", project=project_uuid, runId=run_id)
    _save_manifest(inputs.manifest, evidence_dir)

    config = _build_run_config(args, inputs=inputs, evidence_dir=evidence_dir)
    try:
        return _execute_pipeline(args, config, evidence_dir, evaluation_dir)
    finally:
        if is_repo_url(args.repo):
            cleanup_cloned_repo(str(inputs.src))
        worktree_dir = getattr(args, "_worktree_dir", None)
        worktree_origin = getattr(args, "_worktree_origin", None)
        if worktree_dir and worktree_origin:
            _cleanup_worktree(worktree_origin, worktree_dir)


def run_evaluate(args: argparse.Namespace) -> int:
    """Run the evaluation pipeline."""
    try:
        check_evaluate_prereqs()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
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
