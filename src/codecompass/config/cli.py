import argparse

from codecompass.config import actions
from codecompass.config.actions import ConfigureContext
from codecompass.config.actions import check_sources
from codecompass.config.actions import resolve_parallel
from codecompass.config.actions import run_generate_dimensions
from codecompass.config.actions import run_generate_evaluators
from codecompass.config.actions import run_refresh_analysis
from codecompass.config.actions import run_refresh_practices
from codecompass.config.actions import run_refresh_standards
from codecompass.config.dimensions import render_dimension_table
from codecompass.config.paths import default_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codecompass configure")
    parser.add_argument("--ai-cli", nargs="?")
    parser.add_argument("-d", dest="list_dimensions", action="store_true")
    parser.add_argument("--generate-maps", nargs="?", const="")
    parser.add_argument("--generate-practices")
    parser.add_argument("--generate-dimensions", action="store_true")
    parser.add_argument("--validate-evaluators")
    parser.add_argument("--patch-evaluator", nargs=3)
    parser.add_argument("--check-sources", nargs="?")
    parser.add_argument("--add-discipline", nargs=2)
    parser.add_argument("--list-gaps", nargs="?")
    parser.add_argument("--fill-gap", nargs=2)
    parser.add_argument("--parallel")
    parser.add_argument("--sequential", action="store_true")
    parser.add_argument("--data-version", default=None)
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = default_paths(version=args.data_version)
    _ctx = ConfigureContext(paths=paths, max_parallel=resolve_parallel(args.parallel, args.sequential))
    if args.generate_maps is not None:
        return run_generate_evaluators(args.generate_maps, paths) or 0
    if args.generate_dimensions:
        run_generate_dimensions(paths)
        return 0
    if args.generate_practices is not None:
        return actions.run_generate_practices(args.generate_practices, paths)
    if args.check_sources is not None:
        return check_sources(args.check_sources, paths)
    if args.list_dimensions:
        print(render_dimension_table())
        return 0
    if args.refresh_practices is not None:
        return run_refresh_practices(args.refresh_practices, paths,
                                     min_stars=args.min_stars, dry_run=args.dry_run)
    if args.refresh_analysis is not None:
        return run_refresh_analysis(args.refresh_analysis, paths, dry_run=args.dry_run)
    if args.refresh_standards:
        return run_refresh_standards(paths, dry_run=args.dry_run)
    return 0
