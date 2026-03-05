from __future__ import annotations

import argparse
from dataclasses import dataclass, field

from codecompass.evaluate.lib.usage import evaluate_usage


@dataclass(frozen=True)
class ParseResult:
    discipline: str | None = None
    repo: str | None = None
    dimensions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    no_prescan: bool = False
    evidence_only: bool = False
    numerical: bool = False
    reports_dir: str = "evaluations"
    reports_defaulted: bool = True
    data_version: str | None = None


def parse_cli_args(argv: list[str]) -> ParseResult:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-d", "--dimensions", type=str, default="")
    parser.add_argument("--no-prescan", action="store_true")
    parser.add_argument("--evidence-only", action="store_true")
    parser.add_argument("-n", "--numerical", action="store_true")
    parser.add_argument("--evaluations", type=str, default="evaluations")
    parser.add_argument("--data-version", default=None)
    parser.add_argument("--help", action="store_true")
    parser.add_argument("discipline", nargs="?")
    parser.add_argument("repo", nargs="?")

    reports_defaulted = "--evaluations" not in argv
    args = parser.parse_args(argv)

    if args.repo is None and args.discipline is not None:
        args.repo = args.discipline
        args.discipline = None

    result = ParseResult(
        discipline=args.discipline,
        repo=args.repo,
        dimensions=[d.strip() for d in args.dimensions.split(",") if d.strip()],
        no_prescan=args.no_prescan,
        evidence_only=args.evidence_only,
        numerical=args.numerical,
        reports_dir=args.evaluations,
        reports_defaulted=reports_defaulted,
        data_version=args.data_version,
    )

    if args.help:
        result.errors.append(evaluate_usage())

    if not args.repo:
        result.errors.append("repository path required")

    return result
