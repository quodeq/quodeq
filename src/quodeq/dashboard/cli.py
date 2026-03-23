"""Dashboard CLI — argument parsing and entry point for the dashboard server."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from quodeq.shared.utils import get_dashboard_port, get_evaluations_dir, get_static_dist
from .runner import BuildConfig, DashboardConfig, ServerConfig, run_dashboard

_DEFAULT_STATIC_DIR = Path.home() / ".quodeq" / "static"


def _default_static_dist() -> str:
    """Return the best default for --static-dist."""
    bundled = get_static_dist()
    if bundled:
        return bundled
    return str(_DEFAULT_STATIC_DIR)


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the dashboard command."""
    parser = argparse.ArgumentParser(prog="quodeq dashboard")
    parser.add_argument("--port", type=int, default=get_dashboard_port(),
                        help="Port to run the dashboard server on (default: %(default)s)")
    parser.add_argument("--evaluations", default=get_evaluations_dir(),
                        help="Directory containing evaluation reports (default: %(default)s)")
    parser.add_argument("--static-dist", default=_default_static_dist(),
                        help="Path to the built UI static files (default: %(default)s)")
    parser.add_argument("--repo-root", default=".",
                        help="Root directory of the repository being evaluated (default: %(default)s)")
    parser.add_argument("--api-host", default=None,
                        help="Hostname of an external API server to proxy to")
    parser.add_argument("--api-port", type=int, default=None,
                        help="Port of the external API server (used with --api-host)")
    parser.add_argument("--no-build", action="store_true",
                        help="Skip rebuilding the UI; use cached build (error if none exists)")
    parser.add_argument("--reinstall", action="store_true",
                        help="Force reinstallation of UI dependencies and full rebuild")
    parser.add_argument("--dev", action="store_true", default=False,
                        help=argparse.SUPPRESS)
    parser.add_argument("--open", action=argparse.BooleanOptionalAction, default=True,
                        help="Open the dashboard in a browser after starting (default: %(default)s)")
    return parser


def parse_args(argv: list[str] | None = None) -> DashboardConfig:
    """Parse CLI arguments and return a DashboardConfig."""
    parser = build_parser()
    args = parser.parse_args(argv)
    raw_argv = argv if argv is not None else sys.argv[1:]
    reports_defaulted = "--evaluations" not in raw_argv
    api_forced = "--api-host" in raw_argv or "--api-port" in raw_argv
    return DashboardConfig(
        server=ServerConfig(
            port=args.port,
            api_host=args.api_host,
            api_port=args.api_port,
            api_forced=api_forced,
        ),
        build=BuildConfig(
            open_browser=bool(args.open),
            no_build=args.no_build,
            reinstall=args.reinstall,
            dev=args.dev,
        ),
        reports_dir=Path(args.evaluations),
        static_dist=Path(args.static_dist),
        repo_root=Path(args.repo_root),
        reports_defaulted=reports_defaulted,
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point for the dashboard command."""
    config = parse_args(argv)
    try:
        return run_dashboard(config)
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
