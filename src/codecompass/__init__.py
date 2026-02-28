from codecompass.action_provider import ActionProvider
from codecompass.action_provider_fs import FilesystemActionProvider


def main() -> None:
    from codecompass.cli import main as cli_main

    raise SystemExit(cli_main())
