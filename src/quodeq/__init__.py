"""Quodeq package entry point."""

from quodeq.action_provider import ActionProvider


def main() -> None:
    """Launch the Quodeq CLI."""
    from quodeq.cli import main as cli_main

    raise SystemExit(cli_main())
