import argparse
import sys
from pathlib import Path

from codecompass.adapters.fs.evaluators_repository import FilesystemEvaluatorsRepository
from codecompass.adapters.fs.practices_repository import FilesystemPracticesRepository
from codecompass.bootstrap import DataProvider
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

    dashboard_parser = subparsers.add_parser("dashboard", help="Run the v2 dashboard")
    dashboard_parser.set_defaults(_command="dashboard")

    dashboard_v1_parser = subparsers.add_parser("dashboard-v1", help="Run the legacy v1 dashboard")
    dashboard_v1_parser.set_defaults(_command="dashboard-v1")

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
    evaluate_parser.add_argument(
        "-d",
        "--dimensions",
        default=None,
        help="Comma-separated list of dimension IDs to evaluate (e.g. maintainability,security)",
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
    import uuid

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

    # 5. Parse dimension filter
    dimensions = None
    if args.dimensions:
        dimensions = [d.strip() for d in args.dimensions.split(",") if d.strip()]

    # 6. Build config and run
    config = RunConfig(
        src=src,
        plugin_id=plugin_id,
        evaluators_dir=evaluators_dir,
        source_file_count=source_file_count,
        dimensions=dimensions,
    )

    # 7. Build output directory: <reports>/<project>/<run_id>/
    import json as _json

    reports_root = Path(args.output)
    project_name = src.name
    run_id = uuid.uuid4().hex[:12]
    run_dir = reports_root / project_name / run_id

    # Write repository_info.json so the dashboard can discover this project
    project_dir = reports_root / project_name
    project_dir.mkdir(parents=True, exist_ok=True)
    info_file = project_dir / "repository_info.json"
    if not info_file.exists():
        info = {
            "name": project_name,
            "discipline": plugin_id,
            "location": "online" if is_repo_url(args.repo) else "local",
            "path": str(src),
        }
        info_file.write_text(_json.dumps(info))

    if args.evidence_only:
        import json

        evidence = run(config)
        evidence_dir = run_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        for dim_name in (dimensions or [plugin_id]):
            out_file = evidence_dir / f"{dim_name}_evidence.json"
            out_file.write_text(json.dumps(evidence.to_v1_evidence_dict(), indent=2))
        print(f"Report path: {run_dir / 'evaluation'}")
    else:
        scores = run_full(config, run_dir, mode=args.mode)
        print(f"Report path: {run_dir / 'evaluation'}")
        for dim, score in scores.items():
            print(f"  {dim}: {score}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args._command == "dashboard":
        sub_argv = argv[1:] if argv is not None else sys.argv[2:]
        return dashboard_main(["--version", "v2"] + sub_argv)
    if args._command == "dashboard-v1":
        sub_argv = argv[1:] if argv is not None else sys.argv[2:]
        return dashboard_main(sub_argv)
    if args._command == "evaluate":
        return run_evaluate_v2(args)
    if args._command == "evaluate-v1":
        sub_argv = argv[1:] if argv is not None else sys.argv[2:]
        parsed = parse_cli_args(sub_argv)
        if parsed.errors:
            for err in parsed.errors:
                print(err, file=sys.stderr)
            return 1
        paths = default_paths(version=parsed.data_version)
        provider = DataProvider(
            practices=FilesystemPracticesRepository(root=paths.vroot),
            evaluators=FilesystemEvaluatorsRepository(root=paths.vroot),
        )
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
    if args._command == "configure":
        sub_argv = argv[1:] if argv is not None else sys.argv[2:]
        return configure_main(sub_argv)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
