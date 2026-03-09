import argparse
import sys
from pathlib import Path
from typing import Callable

from codecompass.config.cli import build_parser as build_config_parser
from codecompass.config.cli import main as configure_main
from codecompass.dashboard.cli import main as dashboard_main
from codecompass.util.repo_handler import is_repo_url, prepare_repository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codecompass")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dashboard_parser = subparsers.add_parser("dashboard", help="Run the dashboard")
    dashboard_parser.set_defaults(_command="dashboard")

    evaluate_parser = subparsers.add_parser(
        "evaluate", help="Run evaluation (auto-detects plugin)"
    )
    evaluate_parser.add_argument("repo", help="Path or URL to the repository")
    evaluate_parser.add_argument(
        "-p", "--plugin", default=None, help="Plugin ID (overrides auto-detection)"
    )
    evaluate_parser.add_argument(
        "-o", "--output", default="evaluations", help="Reports output directory"
    )
    evaluate_parser.add_argument(
        "-m",
        "--mode",
        default="numerical",
        choices=["numerical", "grades"],
        help="Scoring mode",
    )
    evaluate_parser.add_argument(
        "--no-prescan", action="store_true", help="Skip source-file counting"
    )
    evaluate_parser.add_argument(
        "-d", "--dimensions", default=None,
        help="Comma-separated dimensions to evaluate (default: all from plugin)",
    )
    evaluate_parser.add_argument(
        "--evidence-only",
        action="store_true",
        help="Produce evidence JSON only (skip scoring)",
    )
    evaluate_parser.set_defaults(_command="evaluate")

    configure_parser = subparsers.add_parser("configure", help="Configure CodeCompass")
    for action in build_config_parser()._actions:
        if "-h" in action.option_strings or "--help" in action.option_strings:
            continue
        if action.option_strings or action.nargs is not None:
            configure_parser._add_action(action)
    configure_parser.set_defaults(_command="configure")

    return parser


def run_evaluate(args: argparse.Namespace) -> int:
    """Run the evaluation pipeline."""
    import uuid as _uuid

    from codecompass.engine.analysis import AnalysisError
    from codecompass.engine.runner import (
        RunConfig,
        count_source_files,
        detect_plugin,
        run,
        run_full,
    )
    from codecompass.engine.plugin_loader import load_plugin
    from codecompass.util.project_resolver import resolve_project_uuid

    # 1. Resolve repo
    repo_path = args.repo
    if is_repo_url(repo_path):
        repo_path = prepare_repository(repo_path)
    src = Path(repo_path).resolve()
    if not src.exists():
        print(f"Repository path does not exist: {src}", file=sys.stderr)
        return 1

    # 2. Locate evaluators directory
    evaluators_dir = Path(__file__).resolve().parents[2] / "evaluators"
    if not evaluators_dir.exists():
        print(f"Evaluators directory not found: {evaluators_dir}", file=sys.stderr)
        return 1

    # 3. Detect or use explicit plugin
    plugin_id = args.plugin
    if plugin_id is None:
        try:
            plugin_id = detect_plugin(src, evaluators_dir)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    print(f"Plugin: {plugin_id}")

    plugin_dir = evaluators_dir / plugin_id
    if not plugin_dir.exists():
        print(f"Plugin directory not found: {plugin_dir}", file=sys.stderr)
        return 1

    # 4. Prescan
    source_file_count = 0
    if not args.no_prescan:
        plugin_data = load_plugin(plugin_dir)
        extensions = set(plugin_data.get("detects", {}).get("extensions", []))
        if extensions:
            source_file_count = count_source_files(src, extensions)
            print(f"Source files: {source_file_count}")

    # 5. Resolve project and create run directory
    reports_root = Path(args.output)
    reports_root.mkdir(parents=True, exist_ok=True)

    project_name = args.repo.split("/")[-1].replace(".git", "") if is_repo_url(args.repo) else Path(args.repo).name
    location = "online" if is_repo_url(args.repo) else "local"
    project_uuid = resolve_project_uuid(reports_root, project_name, str(src), None, location=location)

    run_id = str(_uuid.uuid4())
    evidence_dir = reports_root / project_uuid / run_id / "evidence"
    evaluation_dir = reports_root / project_uuid / run_id / "evaluation"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    print(f"Report path: {evaluation_dir}")

    # 6. Build config and run
    standards_dir = Path(__file__).resolve().parents[2] / "standards"
    dimensions_filter = None
    if args.dimensions:
        dimensions_filter = [d.strip() for d in args.dimensions.split(",") if d.strip()]

    if dimensions_filter:
        print(f"Dimensions: {', '.join(dimensions_filter)}")
    else:
        print("Dimensions: all")

    config = RunConfig(
        src=src,
        plugin_id=plugin_id,
        evaluators_dir=evaluators_dir,
        standards_dir=standards_dir if standards_dir.exists() else None,
        source_file_count=source_file_count,
        dimensions=dimensions_filter,
        work_dir=evidence_dir,
    )

    try:
        if args.evidence_only:
            import json

            evidence = run(config)
            out_file = evidence_dir / f"{plugin_id}_evidence.json"
            out_file.write_text(json.dumps(evidence.to_evidence_dict(), indent=2))
            print(f"Evidence written to {out_file}")
        else:
            scores = run_full(config, evaluation_dir, mode=args.mode)
            print(f"Reports written to {evaluation_dir}/")
            for dim, score in scores.items():
                print(f"  {dim}: {score}")
    except AnalysisError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1

    return 0


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
    parser = build_parser()
    args = parser.parse_args(argv)
    if args._command == "evaluate":
        return run_evaluate(args)
    handler = _COMMAND_HANDLERS.get(args._command)
    if handler:
        return handler(argv)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
