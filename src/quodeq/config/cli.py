"""Command-line interface for the ``quodeq configure`` subcommand."""

from __future__ import annotations

import argparse
from collections.abc import Callable

from quodeq.config.actions import check_sources
from quodeq.config.actions import run_generate_dimensions
from quodeq.config.actions import run_generate_evaluators
from quodeq.config.actions import run_refresh_analysis
from quodeq.config.actions import run_refresh_practices
from quodeq.config.actions import run_refresh_standards
from quodeq.config.actions import run_scaffold_plugin
from quodeq.config.dimensions import render_dimension_table
from quodeq.config.paths import default_paths


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for the configure subcommand."""
    parser = argparse.ArgumentParser(prog="quodeq configure")
    parser.add_argument("--ai-cli", nargs="?",
                        help="AI CLI client to use for configuration tasks (e.g. claude, codex)")
    parser.add_argument("-d", dest="list_dimensions", action="store_true",
                        help="List all available quality dimensions")
    parser.add_argument("--generate-maps", nargs="?", const="",
                        help="Generate evaluator maps for a plugin (omit value to use default)")
    parser.add_argument("--generate-dimensions", action="store_true",
                        help="Generate the dimensions index from evaluator definitions")
    parser.add_argument("--validate-evaluators",
                        help="Validate evaluator files for the given plugin runtime")
    parser.add_argument("--patch-evaluator", nargs=3,
                        metavar=("RUNTIME", "DIMENSION", "PATCH"),
                        help="Apply a JSON patch to an evaluator for the given runtime and dimension")
    parser.add_argument("--check-sources", nargs="?",
                        help="Check data sources for a plugin runtime (omit value to check all)")
    parser.add_argument("--add-discipline", nargs=2, metavar=("RUNTIME", "DISCIPLINE"),
                        help="Add a new discipline to a plugin runtime")
    parser.add_argument("--list-gaps", nargs="?",
                        help="List coverage gaps for a plugin runtime (omit value to list all)")
    parser.add_argument("--fill-gap", nargs=2, metavar=("RUNTIME", "PRINCIPLE"),
                        help="Generate an evaluator to fill a coverage gap for the given principle")
    parser.add_argument("--parallel",
                        help="Number of parallel workers to use for generation tasks")
    parser.add_argument("--sequential", action="store_true",
                        help="Run generation tasks sequentially instead of in parallel")
    parser.add_argument("--data-version", default=None,
                        help="Pin the data version used for generation (default: latest)")
    # Knowledge refresh
    parser.add_argument("--refresh-practices", metavar="RUNTIME",
                        help="Refresh practices.json for a plugin runtime from GitHub cursor-rules")
    parser.add_argument("--refresh-analysis", metavar="RUNTIME",
                        help="Refresh analysis.md for a plugin runtime from linter docs")
    parser.add_argument("--refresh-standards", action="store_true",
                        help="Re-fetch OWASP ASVS L1 into standards/asvs/level1.json")
    parser.add_argument("--min-stars", type=int, default=500,
                        help="Minimum stars for cursor-rules repos (default: 500)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing files")
    # Plugin scaffolding
    parser.add_argument("--scaffold-plugin", metavar="RUNTIME",
                        help="Generate a new plugin skeleton for the given runtime")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate configuration action."""
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = default_paths(version=args.data_version)

    handlers: list[tuple[str, Callable]] = [
        ("generate_maps",       lambda v: run_generate_evaluators(v, paths) or 0),
        ("generate_dimensions", lambda _: (run_generate_dimensions(paths), 0)[1]),
        ("check_sources",       lambda v: check_sources(v, paths)),
        ("list_dimensions",     lambda _: (print(render_dimension_table()), 0)[1]),
        ("refresh_practices",   lambda v: run_refresh_practices(v, paths,
                                     min_stars=args.min_stars, dry_run=args.dry_run)),
        ("refresh_analysis",    lambda v: run_refresh_analysis(v, paths, dry_run=args.dry_run)),
        ("refresh_standards",   lambda _: run_refresh_standards(paths, dry_run=args.dry_run)),
        ("scaffold_plugin",     lambda v: run_scaffold_plugin(v, paths)),
    ]
    for attr, handler in handlers:
        value = getattr(args, attr, None)
        if value is not None and value is not False:
            return handler(value)
    return 0
