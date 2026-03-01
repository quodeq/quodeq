import argparse
import sys
from pathlib import Path

from codecompass.config.cli import build_parser as build_config_parser
from codecompass.config.cli import main as configure_main
from codecompass.dashboard.cli import main as dashboard_main
from codecompass.evaluate import EvaluateConfig, build_parser as build_evaluate_parser
from codecompass.evaluate import run as run_evaluate


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
        reports_defaulted = "--evaluations" not in sub_argv
        discipline = args.discipline
        repo = args.repo
        if repo is None and discipline is not None:
            repo = discipline
            discipline = None
        dimensions = [d.strip() for d in (args.dimensions or "").split(",") if d.strip()]
        config = EvaluateConfig(
            discipline=discipline,
            repo=repo,
            reports_dir=Path(args.evaluations),
            reports_defaulted=reports_defaulted,
            dimensions=dimensions,
            version=getattr(args, "data_version", None),
        )
        return run_evaluate(config)
    if args._command == "configure":
        sub_argv = argv[1:] if argv is not None else sys.argv[2:]
        return configure_main(sub_argv)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
