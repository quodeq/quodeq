"""Dashboard CLI — argument parsing and entry point for the dashboard server."""
import argparse
import sys
from pathlib import Path

from .runner import DashboardConfig, run_dashboard


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the dashboard command."""
    parser = argparse.ArgumentParser(prog="quodeq dashboard")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--evaluations", default="evaluations")
    parser.add_argument("--static-dist", default="ui/web/dist")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--api-host", default=None)
    parser.add_argument("--api-port", type=int, default=None)
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--reinstall", action="store_true")
    parser.add_argument("--open", default="true")
    return parser


def parse_args(argv: list[str] | None = None) -> DashboardConfig:
    """Parse CLI arguments and return a DashboardConfig."""
    parser = build_parser()
    args = parser.parse_args(argv)
    raw_argv = argv if argv is not None else sys.argv[1:]
    reports_defaulted = "--evaluations" not in raw_argv
    api_forced = "--api-host" in raw_argv or "--api-port" in raw_argv
    return DashboardConfig(
        port=args.port,
        reports_dir=Path(args.evaluations),
        static_dist=Path(args.static_dist),
        repo_root=Path(args.repo_root),
        open_browser=args.open.lower() != "false",
        no_build=args.no_build,
        reinstall=args.reinstall,
        reports_defaulted=reports_defaulted,
        api_host=args.api_host,
        api_port=args.api_port,
        api_forced=api_forced,
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point for the dashboard command."""
    config = parse_args(argv)
    return run_dashboard(config)
