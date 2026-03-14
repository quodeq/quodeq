"""Quodeq package entry point."""

from importlib.metadata import version as _pkg_version, PackageNotFoundError

from quodeq.provider.base import ActionProvider

try:
    __version__: str | None = _pkg_version("quodeq")
except PackageNotFoundError:
    __version__ = None


def main() -> None:
    """Launch the Quodeq CLI."""
    from quodeq.cli import main as cli_main

    raise SystemExit(cli_main())
