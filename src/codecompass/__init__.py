from codecompass.action_provider import ActionProvider


def main() -> None:
    from codecompass.cli import main as cli_main

    raise SystemExit(cli_main())
