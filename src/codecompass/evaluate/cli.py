from __future__ import annotations

import argparse

from codecompass.evaluate.lib.cli_parser import ParseResult, parse_cli_args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codecompass evaluate")
    parser.add_argument("discipline", nargs="?")
    parser.add_argument("repo", nargs="?")
    parser.add_argument("-d", "--dimensions", type=str, default="")
    parser.add_argument("--no-prescan", action="store_true")
    parser.add_argument("--evidence-only", action="store_true")
    parser.add_argument("-n", "--numerical", action="store_true")
    parser.add_argument("--evaluations", default="evaluations")
    parser.add_argument("--data-version", default=None)
    return parser


def parse_args(argv: list[str]) -> ParseResult:
    return parse_cli_args(argv)
