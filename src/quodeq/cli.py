"""Command-line interface for Quodeq evaluation and dashboard commands."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Callable

from quodeq.config.cli import build_parser as build_config_parser
from quodeq.config.cli import main as configure_main
from quodeq.config.paths import default_paths
from quodeq.dashboard.cli import main as dashboard_main
from quodeq.engine.analysis import AnalysisError
from quodeq.engine.runner import EvaluationError
from quodeq.engine.plugin_loader import load_plugin
from quodeq.engine.plugin_detector import count_source_files, detect_plugin
from quodeq.engine._runner_report import run_full
from quodeq.engine.runner import AnalysisOptions, RunConfig, run
from quodeq.shared.project_resolver import ProjectIdentity, resolve_project_uuid
from quodeq.shared.repo_handler import prepare_repository
from quodeq.shared.utils import is_repo_url, project_name_from_repo


def _add_evaluate_args(parser: argparse.ArgumentParser) -> None:
    """Register arguments for the evaluate subcommand."""
    parser.add_argument("repo", help="Path or URL to the repository")
    parser.add_argument(
        "-p", "--plugin", default=None, help="Plugin ID (overrides auto-detection)"
    )
    parser.add_argument(
        "-o", "--output", default="evaluations", help="Reports output directory"
    )
    parser.add_argument(
        "-m", "--mode", default="numerical",
        choices=["numerical", "grades"], help="Scoring mode",
    )
    parser.add_argument(
        "--no-prescan", action="store_true", help="Skip source-file counting"
    )
    parser.add_argument(
        "-d", "--dimensions", default=None,
        help="Comma-separated dimensions to evaluate (default: all from plugin)",
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
        "--n-subagents", type=int, default=5,
        help="Number of parallel subagents per dimension (default: 5)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with all subcommands."""
    parser = argparse.ArgumentParser(prog="quodeq")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dashboard_parser = subparsers.add_parser("dashboard", help="Run the dashboard")
    dashboard_parser.set_defaults(handler_command="dashboard")

    evaluate_parser = subparsers.add_parser(
        "evaluate", help="Run evaluation (auto-detects plugin)"
    )
    _add_evaluate_args(evaluate_parser)
    evaluate_parser.set_defaults(handler_command="evaluate")

    configure_parser = subparsers.add_parser(
        "configure", help="Configure Quodeq",
        parents=[build_config_parser()], add_help=False,
    )
    configure_parser.set_defaults(handler_command="configure")

    return parser


def _resolve_repo(args: argparse.Namespace) -> Path | None:
    """Resolve the repo argument to a local path (cloning if needed)."""
    repo_path = args.repo
    if is_repo_url(repo_path):
        try:
            repo_path = prepare_repository(repo_path)
        except Exception as exc:
            print(f"Failed to clone repository: {exc}", file=sys.stderr)
            return None
    src = Path(repo_path).resolve()
    if not src.exists():
        print(f"Repository path does not exist: {src}", file=sys.stderr)
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


def _resolve_plugin(args: argparse.Namespace, src: Path, evaluators_dir: Path) -> str | None:
    """Detect or validate the plugin for a repo. Returns plugin_id or None on error."""
    plugin_id = args.plugin
    if plugin_id is None:
        try:
            plugin_id = detect_plugin(src, evaluators_dir)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return None
    print(f"Plugin: {plugin_id}")
    plugin_dir = evaluators_dir / plugin_id
    if not plugin_dir.exists():
        print(f"Plugin directory not found: {plugin_dir}", file=sys.stderr)
        return None
    return plugin_id


def _prescan_sources(args: argparse.Namespace, plugin_dir: Path, src: Path) -> int:
    """Count source files for the plugin if prescan is not disabled."""
    if args.no_prescan:
        return 0
    plugin_data = load_plugin(plugin_dir)
    extensions = set(plugin_data.get("detects", {}).get("extensions", []))
    if not extensions:
        return 0
    source_file_count = count_source_files(src, extensions)
    print(f"Source files: {source_file_count}")
    return source_file_count


def _execute_pipeline(args: argparse.Namespace, config: RunConfig, evidence_dir: Path, evaluation_dir: Path) -> int:
    """Execute the evidence/scoring pipeline and print results."""
    try:
        if args.evidence_only:
            evidence = run(config)
            out_file = evidence_dir / f"{config.plugin_id}_evidence.json"
            out_file.write_text(json.dumps(evidence.to_evidence_dict(), indent=2))
            print(f"Evidence written to {out_file}")
        else:
            scores = run_full(config, evaluation_dir, mode=args.mode)
            print(f"Reports written to {evaluation_dir}/")
            for dim, score in scores.items():
                print(f"  {dim}: {score}")
    except (AnalysisError, EvaluationError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1
    return 0


def run_evaluate(args: argparse.Namespace) -> int:
    """Run the evaluation pipeline."""
    src = _resolve_repo(args)
    if src is None:
        return 1

    evaluators_dir = default_paths().evaluators_dir
    if not evaluators_dir.exists():
        print(f"Evaluators directory not found: {evaluators_dir}", file=sys.stderr)
        return 1

    plugin_id = _resolve_plugin(args, src, evaluators_dir)
    if plugin_id is None:
        return 1

    source_file_count = _prescan_sources(args, evaluators_dir / plugin_id, src)
    _reports_root, evidence_dir, evaluation_dir = _setup_run_dirs(args, src)
    print(f"Report path: {evaluation_dir}")

    standards_dir = default_paths().standards_dir
    dimensions_filter = [d.strip() for d in args.dimensions.split(",") if d.strip()] if args.dimensions else None
    print(f"Dimensions: {', '.join(dimensions_filter)}" if dimensions_filter else "Dimensions: all")

    config = RunConfig(
        src=src,
        plugin_id=plugin_id,
        evaluators_dir=evaluators_dir,
        standards_dir=standards_dir if standards_dir.exists() else None,
        source_file_count=source_file_count,
        work_dir=evidence_dir,
        options=AnalysisOptions(
            dimensions=dimensions_filter,
            max_turns=args.max_turns,
            max_duration=args.max_duration,
            n_subagents=args.n_subagents,
            subagent_model=os.environ.get("SUBAGENT_MODEL") or None,
        ),
    )

    return _execute_pipeline(args, config, evidence_dir, evaluation_dir)


def _run_dashboard(argv: list[str] | None) -> int:
    sub_argv = argv[1:] if argv is not None else sys.argv[2:]
    return dashboard_main(sub_argv)


def _run_configure(argv: list[str] | None) -> int:
    sub_argv = argv[1:] if argv is not None else sys.argv[2:]
    return configure_main(sub_argv)


_COMMAND_HANDLERS: dict[str, Callable] = {
    "dashboard": _run_dashboard,
    "configure": _run_configure,
}


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate subcommand handler."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.handler_command == "evaluate":
        return run_evaluate(args)
    handler = _COMMAND_HANDLERS.get(args.handler_command)
    if handler:
        return handler(argv)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
