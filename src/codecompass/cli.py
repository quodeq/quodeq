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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codecompass")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dashboard_parser = subparsers.add_parser("dashboard", help="Run the dashboard")
    dashboard_parser.set_defaults(_command="dashboard")

    evaluate_parser = subparsers.add_parser("evaluate", help="Run evaluation")
    for action in build_evaluate_parser()._actions:
        if "-h" in action.option_strings or "--help" in action.option_strings:
            continue
        if action.option_strings or action.nargs is not None:
            evaluate_parser._add_action(action)
    evaluate_parser.set_defaults(_command="evaluate")

    configure_parser = subparsers.add_parser("configure", help="Configure CodeCompass")
    for action in build_config_parser()._actions:
        if "-h" in action.option_strings or "--help" in action.option_strings:
            continue
        if action.option_strings or action.nargs is not None:
            configure_parser._add_action(action)
    configure_parser.set_defaults(_command="configure")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args._command == "dashboard":
        sub_argv = argv[1:] if argv is not None else sys.argv[2:]
        return dashboard_main(sub_argv)
    if args._command == "evaluate":
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
