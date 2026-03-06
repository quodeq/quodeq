import argparse
import sys
from pathlib import Path
from typing import Callable

from codecompass.config.cli import build_parser as build_config_parser
from codecompass.config.cli import main as configure_main
from codecompass.config.paths import default_paths
from codecompass.dashboard.cli import main as dashboard_main
from codecompass.evaluate import EvaluateConfig, build_parser as build_evaluate_parser
from codecompass.evaluate import run as run_evaluate
from codecompass.evaluate.lib.cli_parser import parse_cli_args
from codecompass.evaluate.lib.repo_handler import is_repo_url, prepare_repository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codecompass")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dashboard_parser = subparsers.add_parser("dashboard", help="Run the dashboard")
    dashboard_parser.set_defaults(_command="dashboard")

    # v2 evaluate (default)
    evaluate_parser = subparsers.add_parser(
        "evaluate", help="Run v2 evaluation (auto-detects plugin)"
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
        "--evidence-only",
        action="store_true",
        help="Produce evidence JSON only (skip scoring)",
    )
    evaluate_parser.set_defaults(_command="evaluate")

    # v1 evaluate (legacy, explicit discipline)
    evaluate_v1_parser = subparsers.add_parser(
        "evaluate-v1", help="Run v1 evaluation (explicit discipline)"
    )
    for action in build_evaluate_parser()._actions:
        if "-h" in action.option_strings or "--help" in action.option_strings:
            continue
        if action.option_strings or action.nargs is not None:
            evaluate_v1_parser._add_action(action)
    evaluate_v1_parser.set_defaults(_command="evaluate-v1")

    configure_parser = subparsers.add_parser("configure", help="Configure CodeCompass")
    for action in build_config_parser()._actions:
        if "-h" in action.option_strings or "--help" in action.option_strings:
            continue
        if action.option_strings or action.nargs is not None:
            configure_parser._add_action(action)
    configure_parser.set_defaults(_command="configure")

    return parser


def run_evaluate_v2(args: argparse.Namespace) -> int:
    """Run the v2 evaluation pipeline."""
    from codecompass.v2.engine.runner import (
        RunConfig,
        count_source_files,
        detect_plugin,
        run,
        run_full,
    )
    from codecompass.v2.engine.plugin_loader import load_plugin

    # 1. Resolve repo
    repo_path = args.repo
    if is_repo_url(repo_path):
        repo_path = prepare_repository(repo_path)
    src = Path(repo_path).resolve()
    if not src.exists():
        print(f"Repository path does not exist: {src}", file=sys.stderr)
        return 1

    # 2. Locate evaluators directory
    evaluators_dir = Path(__file__).resolve().parents[2] / "v2" / "evaluators"
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

    # 5. Build config and run
    standards_dir = Path(__file__).resolve().parents[2] / "v2" / "standards"
    config = RunConfig(
        src=src,
        plugin_id=plugin_id,
        evaluators_dir=evaluators_dir,
        standards_dir=standards_dir if standards_dir.exists() else None,
        source_file_count=source_file_count,
    )

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    config.work_dir = output_dir

    if args.evidence_only:
        import json

        evidence = run(config)
        out_file = output_dir / f"{plugin_id}_evidence.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(evidence.to_v1_evidence_dict(), indent=2))
        print(f"Evidence written to {out_file}")
    else:
        scores = run_full(config, output_dir, mode=args.mode)
        print(f"Reports written to {output_dir}/")
        for dim, score in scores.items():
            print(f"  {dim}: {score}")

    return 0


def _run_dashboard(argv: list[str] | None) -> int:
    sub_argv = argv[1:] if argv is not None else sys.argv[2:]
    return dashboard_main(sub_argv)


def _run_evaluate_v1(argv: list[str] | None) -> int:
    sub_argv = argv[1:] if argv is not None else sys.argv[2:]
    parsed = parse_cli_args(sub_argv)
    if parsed.errors:
        for err in parsed.errors:
            print(err, file=sys.stderr)
        return 1
    paths = default_paths(version=parsed.data_version)
    from codecompass.bootstrap import default_provider
    provider = default_provider(paths.vroot)
    config = EvaluateConfig(
        discipline=parsed.discipline,
        repo=parsed.repo,
        reports_dir=Path(parsed.reports_dir),
        reports_defaulted=parsed.reports_defaulted,
        dimensions=parsed.dimensions,
        evidence_only=parsed.evidence_only,
        no_prescan=parsed.no_prescan,
        numerical=parsed.numerical,
        version=parsed.data_version,
        provider=provider,
    )
    return run_evaluate(config)


def _run_configure(argv: list[str] | None) -> int:
    sub_argv = argv[1:] if argv is not None else sys.argv[2:]
    return configure_main(sub_argv)


_COMMAND_HANDLERS: dict[str, Callable] = {
    "dashboard": _run_dashboard,
    "evaluate-v1": _run_evaluate_v1,
    "configure": _run_configure,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args._command == "evaluate":
        return run_evaluate_v2(args)
    handler = _COMMAND_HANDLERS.get(args._command)
    if handler:
        return handler(argv)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
