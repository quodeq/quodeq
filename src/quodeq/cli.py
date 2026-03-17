"""Command-line interface for Quodeq evaluation and dashboard commands."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Callable

from quodeq.config.paths import default_paths, load_env_file
from quodeq.dashboard.cli import main as dashboard_main
from quodeq.analysis.subprocess import AnalysisError
from quodeq.analysis.runner import AnalysisOptions, EvaluationError, RunConfig, run
from quodeq.core.scoring.report import run_full
from quodeq.shared.project_resolver import ProjectIdentity, resolve_project_uuid
from quodeq.shared.repo_handler import prepare_repository
from quodeq.shared.utils import get_evaluations_dir, is_repo_url, project_name_from_repo, write_text
from quodeq.shared.validation import validate_path_segment


_DEFAULT_N_SUBAGENTS = 5
_MODE_NUMERICAL = "numerical"
_MODE_GRADES = "grades"
_ENV_MAX_TURNS = "QUODEQ_MAX_TURNS"
_ENV_MAX_DURATION = "QUODEQ_MAX_DURATION"


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


def _add_evaluate_args(parser: argparse.ArgumentParser) -> None:
    """Register arguments for the evaluate subcommand."""
    parser.add_argument("repo", help="Path or URL to the repository")
    parser.add_argument(
        "-l", "--language", default=None, help="Language (overrides auto-detection)"
    )
    parser.add_argument(
        "-o", "--output", default=get_evaluations_dir(), help="Reports output directory"
    )
    parser.add_argument(
        "-m", "--mode", default=_MODE_NUMERICAL,
        choices=[_MODE_NUMERICAL, _MODE_GRADES], help="Scoring mode",
    )
    parser.add_argument(
        "--no-prescan", action="store_true", help="Skip source-file counting"
    )
    parser.add_argument(
        "-d", "--dimensions", default=None,
        help="Comma-separated dimensions to evaluate (default: all)",
    )
    parser.add_argument(
        "--evidence-only", action="store_true",
        help="Produce evidence JSON only (skip scoring)",
    )
    parser.add_argument(
        "--max-turns", type=int, default=None,
        help="Max AI conversation turns per dimension (default: 200)",
    )
    parser.add_argument(
        "--max-duration", type=int, default=None,
        help="Max seconds per dimension before terminating (default: 1800)",
    )
    parser.add_argument(
        "--n-subagents", type=int, default=_DEFAULT_N_SUBAGENTS,
        help="Number of parallel subagents per dimension (default: %(default)s)",
    )
    parser.add_argument(
        "--no-verify", action="store_true",
        help="Skip post-analysis verification pass",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with all subcommands."""
    parser = argparse.ArgumentParser(prog="quodeq")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dashboard_parser = subparsers.add_parser("dashboard", help="Run the dashboard")
    dashboard_parser.set_defaults(handler_command="dashboard")

    evaluate_parser = subparsers.add_parser(
        "evaluate", help="Run evaluation (auto-detects language)"
    )
    _add_evaluate_args(evaluate_parser)
    evaluate_parser.set_defaults(handler_command="evaluate")

    return parser


def _resolve_repo(args: argparse.Namespace) -> Path | None:
    """Resolve the repo argument to a local path (cloning if needed)."""
    repo_path = args.repo
    # NOTE: print() here uses plain text only.  If ANSI escapes are added in
    # the future, gate them on the NO_COLOR environment variable.
    if is_repo_url(repo_path):
        try:
            repo_path = prepare_repository(repo_path)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as exc:
            print(f"Failed to clone repository: {exc}", file=sys.stderr)
            return None
    src = Path(repo_path).resolve()
    if not src.exists():
        print(f"Repository path does not exist: {src}. Verify the path is correct and accessible.", file=sys.stderr)
        return None
    return src


def _setup_run_dirs(args: argparse.Namespace, src: Path) -> tuple[Path, Path, Path]:
    """Resolve project UUID and create evidence/evaluation directories."""
    reports_root = Path(args.output)
    reports_root.mkdir(parents=True, exist_ok=True)

    project_name = project_name_from_repo(args.repo)
    location = "online" if is_repo_url(args.repo) else "local"
    project_uuid = resolve_project_uuid(reports_root, ProjectIdentity(project_name, str(src), None, location))

    run_id = str(uuid.uuid4())
    evidence_dir = reports_root / project_uuid / run_id / "evidence"
    evaluation_dir = reports_root / project_uuid / run_id / "evaluation"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    return reports_root, evidence_dir, evaluation_dir



def _resolve_language(args: argparse.Namespace, src: Path, paths) -> str | None:
    """Detect or validate the language for a repo using universal detection.

    Returns language string or None on error.
    """
    if args.language:
        validate_path_segment(args.language)
        return args.language

    detection_file = paths.detection_file
    if not detection_file.exists():
        return None

    try:
        from quodeq.analysis.manifest import detect_language
        language = detect_language(src, detection_file)
        return language
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return None


def _build_manifest(args: argparse.Namespace, src: Path, paths) -> "SourceManifest | None":
    """Build a source manifest for the repository."""
    if args.no_prescan:
        return None

    from quodeq.analysis.manifest import SourceManifest, build_manifest
    from quodeq.shared.utils import read_json

    detection_file = paths.detection_file
    if not detection_file.exists():
        return None

    detection = read_json(detection_file)
    disciplines_conf = paths.disciplines_conf if paths.disciplines_conf.exists() else None
    manifest = build_manifest(src, detection, disciplines_conf)
    if manifest.targets:
        langs = ", ".join(
            f"{t.project_description} ({t.total_files})"
            for t in manifest.targets
        )
        print(f"Detected: {langs}", file=sys.stderr)
    print(f"Source files: {manifest.total_files}", file=sys.stderr)
    return manifest



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
            print(f"Reports written to {evaluation_dir}/", file=sys.stderr)
            for dim, score in scores.items():
                print(f"  {dim}: {score}")
    except (AnalysisError, EvaluationError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1
    return 0


def _no_verify(args: argparse.Namespace, env: dict[str, str] | None = None) -> bool:
    """Return True if verification should be skipped (CLI flag or env var)."""
    return args.no_verify or (env or os.environ).get("QUODEQ_NO_VERIFY") == "1"


def _build_run_config(
    args: argparse.Namespace, src: Path, language: str,
    manifest, dims_data: dict, evidence_dir: Path,
) -> RunConfig:
    """Assemble a RunConfig from CLI args and resolved paths."""
    standards_dir = default_paths().standards_dir
    dimensions_filter = [d.strip() for d in args.dimensions.split(",") if d.strip()] if args.dimensions else None
    print(f"Dimensions: {', '.join(dimensions_filter)}" if dimensions_filter else "Dimensions: all", file=sys.stderr)

    return RunConfig(
        src=src,
        language=language,
        standards_dir=standards_dir if standards_dir.exists() else None,
        work_dir=evidence_dir,
        manifest=manifest,
        dimensions_data=dims_data,
        options=AnalysisOptions(
            dimensions=dimensions_filter,
            max_turns=args.max_turns if args.max_turns is not None else _env_int(_ENV_MAX_TURNS, None),
            max_duration=args.max_duration if args.max_duration is not None else _env_int(_ENV_MAX_DURATION, None),
            n_subagents=args.n_subagents,
            subagent_model=_subagent_model(),
            verify_findings=not _no_verify(args),
        ),
    )


def run_evaluate(args: argparse.Namespace) -> int:
    """Run the evaluation pipeline."""
    src = _resolve_repo(args)
    if src is None:
        return 1

    paths = default_paths()

    if not paths.detection_file.exists() or not paths.dimensions_file.exists():
        print("Configuration not found: detection.json and dimensions.json are required.", file=sys.stderr)
        return 1

    language = _resolve_language(args, src, paths)
    if language is None:
        return 1

    from quodeq.analysis.runner import load_universal_dimensions
    try:
        dims_data = load_universal_dimensions(paths.dimensions_file)
    except ValueError as exc:
        print(f"Invalid dimensions config: {exc}", file=sys.stderr)
        return 1

    manifest = _build_manifest(args, src, paths)
    _reports_root, evidence_dir, evaluation_dir = _setup_run_dirs(args, src)
    print(f"Report path: {evaluation_dir}", file=sys.stderr)

    # Save manifest for debugging
    if manifest and evidence_dir:
        try:
            write_text(
                evidence_dir / "manifest.json",
                json.dumps(manifest.to_dict(), indent=2),
            )
        except OSError:
            pass  # non-critical

    # Single-pass analysis: all files in one unified queue per dimension.
    # The AI analyzes each file according to its language naturally.
    config = _build_run_config(args, src, language, manifest, dims_data, evidence_dir)
    return _execute_pipeline(args, config, evidence_dir, evaluation_dir)


def _run_dashboard(argv: list[str] | None) -> int:
    sub_argv = argv[1:] if argv is not None else sys.argv[2:]
    return dashboard_main(sub_argv)


_COMMAND_HANDLERS: dict[str, Callable] = {
    "dashboard": _run_dashboard,
}


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate subcommand handler."""
    load_env_file(default_paths())
    parser = build_parser()
    args, remaining = parser.parse_known_args(argv)
    if args.handler_command == "evaluate":
        return run_evaluate(args)
    handler = _COMMAND_HANDLERS.get(args.handler_command)
    if handler:
        return handler(argv)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
